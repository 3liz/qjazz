//!
//! Pipe communication
//!
//!
use nix::{errno::Errno, unistd};
use serde::{de, Deserialize, Deserializer};
use serde_pickle as pickle;
use std::fmt;
use std::marker::PhantomData;
use std::ops::ControlFlow;
use std::os::fd::{AsRawFd, RawFd};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::process::{ChildStdin, ChildStdout};

use crate::errors::{Error, Result};
use crate::messages::{Envelop, JsonValue, Message, Pickable, RequestReport};

pub(crate) struct Pipe {
    //stdin: ChildStdin,
    stdin: ChildStdin,
    stdout: ChildStdout,
    buffer: Vec<u8>,
}

/// Options for Pipe
pub(crate) struct PipeOptions {
    pub buffer_size: usize,
}

/// Communicate with stdout/stdin of child process
///
/// Each chunk of data send by the childe process is always
/// preceded by a big-endian 32 integer whose value is the size
/// of the chunk of bytes that follows.
impl Pipe {
    pub fn new(stdin: ChildStdin, stdout: ChildStdout, options: PipeOptions) -> Self {
        Self {
            stdin,
            stdout,
            buffer: vec![0; options.buffer_size],
        }
    }

    /// Send message to pipe
    pub async fn put_message<T>(&mut self, msg: Message<T>) -> Result<()>
    where
        T: Pickable,
    {
        let buf = pickle::to_vec(&msg, Default::default())?;
        self.stdin
            .write_all(&(buf.len() as i32).to_be_bytes())
            .await?;
        self.stdin.write_all(buf.as_slice()).await?;
        Ok(())
    }

    /// Pull out all remaining data from output pipe
    /// Until it would block or return 0
    pub async fn drain(&mut self) -> Result<bool> {
        let fd = self.stdout.as_raw_fd();
        let mut buf = [0u8; 1];
        // Test if there is data waiting by reading only one byte
        // Otherwise block while reading remaining input
        // NOTE: assume that the file descriptor is in non blocking mode
        // which is usually the case with fd opened through async call.
        match unistd::read(fd, &mut buf) {
            Ok(0) | Err(Errno::EWOULDBLOCK) => Ok(false),
            Ok(_) => self.drain_blocking(fd).await, // Pull out remaining data
            Err(errno) => {
                log::error!("Drain: I/O error: {:#?}", errno);
                Err(Error::from(errno))
            }
        }
    }

    async fn drain_blocking(&mut self, fd: RawFd) -> Result<bool> {
        // Run as blocking: reading directy will block so
        // it may take some time for large data.
        match tokio::task::spawn_blocking(move || {
            let mut buffer = Vec::<u8>::with_capacity(4096);
            let mut len = 0;
            // SAFETY: buf is waste container used to drain data and it will
            // not go anywhere.
            let buf: &mut [u8] = unsafe { std::mem::transmute(buffer.spare_capacity_mut()) };
            loop {
                log::trace!("Entering blocking i/o drain...");
                match unistd::read(fd, buf) {
                    Ok(0) | Err(Errno::EWOULDBLOCK) => return Ok(len > 0),
                    Ok(n) => len += n,
                    Err(errno) => {
                        log::error!("Drain: I/O error: {:#?}", errno);
                        return Err(Error::from(errno));
                    }
                }
            }
        })
        .await
        {
            Ok(rv) => rv,
            Err(err) => {
                if !err.is_cancelled() {
                    log::error!("Drain task failed:  {:?}", err);
                    Err(Error::TaskFailed("Drain task failed".to_string()))
                } else {
                    log::trace!("Drain finished");
                    Ok(true)
                }
            }
        }
    }

    /// Read bytes chunk
    pub async fn read_bytes(&mut self) -> Result<Option<&[u8]>> {
        match self.stdout.read_i32().await? as usize {
            size if size > self.buffer.capacity() => Err(Error::IoBufferOverflow),
            size if size > 0 => {
                let buf = &mut self.buffer[..size];
                let mut len = self.stdout.read(buf).await?;
                while len < size {
                    len += self.stdout.read(&mut buf[len..]).await?;
                }
                Ok(Some(&self.buffer[..size]))
            }
            _ => Ok(None),
        }
    }

    /// Read NoData response
    pub async fn read_nodata(&mut self) -> Result<()> {
        if let Some(bytes) = self.read_bytes().await? {
            match pickle::from_reader(bytes, Default::default())? {
                Envelop::<JsonValue>::NoData => Ok(()),
                Envelop::Success(status, msg) => Err(Error::ResponseError(status, msg)),
                Envelop::Failure(status, msg) => Err(Error::ResponseError(status, msg)),
                Envelop::ByteChunk => Err(Error::UnexpectedResponse),
            }
        } else {
            Err(Error::ResponseExpected)
        }
    }

    /// Read response data
    pub async fn read_response<'de, T: Deserialize<'de>>(&mut self) -> Result<(i64, T)> {
        if let Some(bytes) = self.read_bytes().await? {
            match pickle::from_reader(bytes, Default::default())? {
                Envelop::Success(status, msg) => Ok((status, msg)),
                Envelop::Failure(status, msg) => Err(Error::ResponseError(status, msg)),
                Envelop::NoData => Err(Error::NoDataResponse),
                Envelop::ByteChunk => Err(Error::UnexpectedResponse),
            }
        } else {
            Err(Error::ResponseExpected)
        }
    }

    /// Read streamed response
    pub async fn read_stream<'de, T: Deserialize<'de>>(
        &mut self,
    ) -> Result<ControlFlow<Option<T>, T>> {
        if let Some(bytes) = self.read_bytes().await? {
            match pickle::from_reader(bytes, Default::default())? {
                Envelop::Success(status, msg) => {
                    if status == 206 {
                        Ok(ControlFlow::Continue(msg))
                    } else {
                        Ok(ControlFlow::Break(Some(msg)))
                    }
                }
                Envelop::Failure(status, msg) => Err(Error::ResponseError(status, msg)),
                Envelop::NoData => Ok(ControlFlow::Break(None)),
                Envelop::ByteChunk => Err(Error::UnexpectedResponse),
            }
        } else {
            Err(Error::ResponseExpected)
        }
    }

    /// Read stream bytes chunk response
    pub async fn read_chunk(&mut self) -> Result<ControlFlow<(), &[u8]>> {
        if let Some(bytes) = self.read_bytes().await? {
            match pickle::from_reader(bytes, Default::default())? {
                Envelop::<JsonValue>::ByteChunk => {
                    if let Some(bytes) = self.read_bytes().await? {
                        Ok(ControlFlow::Continue(bytes))
                    } else {
                        Err(Error::EmptyChunk)
                    }
                }
                Envelop::NoData => Ok(ControlFlow::Break(())),
                Envelop::Failure(status, msg) => Err(Error::ResponseError(status, msg)),
                Envelop::Success(status, msg) => Err(Error::ResponseError(status, msg)),
            }
        } else {
            Err(Error::ResponseExpected)
        }
    }

    /// Read report data
    pub async fn read_report(&mut self) -> Result<RequestReport> {
        if let Some(bytes) = self.read_bytes().await? {
            pickle::from_reader(bytes, Default::default()).map_err(Error::PickleError)
        } else {
            Err(Error::ResponseExpected)
        }
    }

    /// Send a message and wait for return
    pub async fn send_message<'de, R>(&mut self, msg: impl Pickable) -> Result<(i64, R)>
    where
        R: Deserialize<'de>,
    {
        self.put_message(msg.into()).await?;
        self.read_response().await
    }

    /// Send a message that expect no return data
    pub async fn send_nodata_message(&mut self, msg: impl Pickable) -> Result<()> {
        self.put_message(msg.into()).await?;
        self.read_nodata().await
    }
}

//
// Implement deserializer for envelop
impl<'de, T> Deserialize<'de> for Envelop<T>
where
    T: Deserialize<'de>,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        // We need to constrain the generic parameter T
        struct EnvelopVisitor<T>(PhantomData<T>);

        // Envelop is serialized a tuple (status, msg)
        impl<'de, T> de::Visitor<'de> for EnvelopVisitor<T>
        where
            T: Deserialize<'de>,
        {
            type Value = Envelop<T>;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("Expecting sequence (int, <any>) or integer value 204")
            }

            fn visit_i64<E>(self, v: i64) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                match v {
                    204 => Ok(Envelop::NoData),
                    206 => Ok(Envelop::ByteChunk),
                    _ => Err(de::Error::invalid_value(de::Unexpected::Signed(v), &self)),
                }
            }

            fn visit_seq<V>(self, mut seq: V) -> Result<Self::Value, V::Error>
            where
                V: de::SeqAccess<'de>,
            {
                let status: i64 = seq
                    .next_element()?
                    .ok_or_else(|| de::Error::invalid_length(0, &self))?;
                match status {
                    200 | 206 => Ok(Envelop::Success(
                        status,
                        seq.next_element()?
                            .ok_or_else(|| de::Error::invalid_length(1, &self))?,
                    )),
                    _ => Ok(Envelop::Failure(
                        status,
                        seq.next_element()?
                            .ok_or_else(|| de::Error::invalid_length(1, &self))?,
                    )),
                }
            }
        }

        deserializer.deserialize_seq(EnvelopVisitor::<T>(PhantomData))
    }
}

// =======================
// Tests
// =======================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::messages::PluginInfo;
    use serde_json::json;

    #[test]
    fn test_envelop_success_de() {
        let envelop_ok = (
            200,
            PluginInfo {
                name: "my_plugin".into(),
                path: "/the/path".into(),
                plugin_type: "server".into(),
                metadata: json!({
                    "general":  {
                        "name": "foo",
                        "qgisMinimumVersion": "3.0"
                    }
                }),
            },
        );
        let mut buf = Vec::new();
        pickle::to_writer(&mut buf, &envelop_ok, Default::default()).unwrap();

        let rv: Envelop<PluginInfo> = pickle::from_reader(&buf[..], Default::default()).unwrap();
        assert_eq!(rv, Envelop::Success(200, envelop_ok.1));
    }

    #[test]
    fn test_envelop_failure_de() {
        let envelop_fail = (400, json!("failure"));
        let mut buf = Vec::new();
        pickle::to_writer(&mut buf, &envelop_fail, Default::default()).unwrap();

        let rv: Envelop<PluginInfo> = pickle::from_reader(&buf[..], Default::default()).unwrap();
        assert_eq!(rv, Envelop::Failure(400, envelop_fail.1));
    }

    #[test]
    fn test_envelop_nodata() {
        let mut buf = Vec::new();

        pickle::to_writer(&mut buf, &204, Default::default()).unwrap();
        let rv_ok: Envelop<PluginInfo> = pickle::from_reader(&buf[..], Default::default()).unwrap();
        assert_eq!(rv_ok, Envelop::NoData);

        // Test invalid no data status code
        pickle::to_writer(&mut buf, &999, Default::default()).unwrap();
        let rv_err: Result<Envelop<PluginInfo>, _> =
            pickle::from_reader(&buf[..], Default::default());
        assert!(rv_err.is_err());
    }
}
