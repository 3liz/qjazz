mod config;
mod logger;
mod server;
mod service;
mod signals;

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
        #[arg(long, short = 'C', value_name = "FILE")]
        conf: Option<PathBuf>,
    },
    /// Run grpc server
    Serve {
        #[arg(long, short = 'C', value_name = "FILE")]
        conf: Option<PathBuf>,
    },
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Cli::parse();

    match &args.command {
        Some(Commands::Settings) => {
            println!("TODO!");
        }
        Some(Commands::Config { conf }) => {
            let settings = match conf {
                Some(conf) => Settings::from_file_template(conf)?,
                None => Settings::new()?,
            };
            serde_json::to_writer_pretty(io::stdout().lock(), &settings)?;
        }
        Some(Commands::Serve { conf }) => {
            let settings = match conf {
                Some(conf) => Settings::from_file_template(conf)?,
                None => Settings::new()?,
            };
            let mapserv_args = std::env::var_os("QJAZZ_MAPSERV_ARGS");

            settings.init_logger();
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()?
                .block_on(serve(
                    mapserv_args
                        .as_ref()
                        .and_then(|v| v.to_str())
                        .unwrap_or("-m qjazz_rpc.main"),
                    &settings,
                ))?;
        }
        None => (),
    }
    Ok(())
}

const CLAP_STYLE: clap::builder::styling::Styles = clap::builder::styling::Styles::plain();
