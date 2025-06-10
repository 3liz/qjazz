//!
//! Implement stream-like obects from Pipe
//!
use crate::errors::Result;
use crate::pipes::Pipe;
use serde::de;
use std::marker::PhantomData;
use std::ops::ControlFlow;

/// Async streamlike object for bytes
pub struct ByteStream<'a> {
    io: &'a mut Pipe,
    done: bool,
}

impl<'a> ByteStream<'a> {
    pub(crate) fn new(io: &'a mut Pipe) -> Self {
        Self { io, done: false }
    }

    /// Get result as shared data
    pub async fn next(&mut self) -> Result<Option<&[u8]>> {
        if self.done {
            return Ok(None);
        }
        self.io
            .read_chunk()
            .await
            .map(|control| match control {
                ControlFlow::Continue(data) => Some(data),
                ControlFlow::Break(()) => {
                    self.done = true;
                    None
                }
            })
            .inspect_err(|_| {
                self.done = true;
            })
    }
}

/// Async streamlike object for response object
pub struct ObjectStream<'a, T> {
    io: &'a mut Pipe,
    done: bool,
    return_type: PhantomData<T>,
}

impl<'a, T> ObjectStream<'a, T>
where
    T: de::DeserializeOwned,
{
    pub(crate) fn new(io: &'a mut Pipe) -> Self {
        Self {
            io,
            done: false,
            return_type: PhantomData,
        }
    }

    /// Return Some(element) if any or None if there is
    /// no element left in the stream.
    pub async fn next(&mut self) -> Result<Option<T>> {
        if self.done {
            return Ok(None);
        }
        self.io
            .read_stream()
            .await
            .map(|control| match control {
                ControlFlow::Continue(v) => Some(v),
                ControlFlow::Break(v) => {
                    self.done = true;
                    v
                }
            })
            .inspect_err(|_| {
                self.done = true;
            })
    }
}
