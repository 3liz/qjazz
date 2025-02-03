// Complile service protos
// see https://docs.rs/tonic-build/latest/tonic_build/

// Download the protoc compiler
// wget -qO protoc.zip
// https://github.com/protocolbuffers/protobuf/releases/latest/download/protoc-29.1-linux-x86_64.zip

fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::configure()
        .build_server(false)
        // Uncomment the following for exporting in json
        //.type_attribute(".", "#[derive(Serialize)]");
        //.type_attribute(".", "#[serde(rename_all = \"camelCase\")]");
        .compile_protos(&["proto/qjazz.proto"], &["proto"])?;
    Ok(())
}
