mod config;
mod logger;
mod server;
mod service;

use server::serve;

use clap::{Parser, Subcommand};
use config::Settings;
use std::io::{self, Write};
use std::path::PathBuf;

#[derive(Parser)]
#[command(version, author, about, long_about=None)]
#[command(arg_required_else_help = true)]
#[command(styles = CLAP_STYLE)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Show QGIS settings
    Settings,
    /// Print configuration in json format
    Config {
        /// Print configuration and exit
        #[arg(long, value_name = "FILE")]
        conf: PathBuf,
    },
    /// Run grpc server
    Serve {
        #[arg(long, value_name = "FILE")]
        conf: PathBuf,
    },
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Cli::parse();

    match &args.command {
        Some(Commands::Settings) => {
            println!("TODO!");
        }
        Some(Commands::Config { conf }) => {
            serde_json::to_writer_pretty(
                io::stdout().lock(),
                &Settings::from_file_template(conf)?,
            )?;
        }
        Some(Commands::Serve { conf }) => {
            let settings = Settings::from_file_template(conf)?;
            settings.init_logger();
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()?
                .block_on(serve(["../qjazz-pool/tests/process.py"], &settings))?;
        }
        None => (),
    }
    Ok(())
}

const CLAP_STYLE: clap::builder::styling::Styles = clap::builder::styling::Styles::plain();
