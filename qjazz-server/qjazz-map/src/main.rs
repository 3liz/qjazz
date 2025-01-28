mod channel;
mod config;
mod cors;
mod handlers;
mod logger;
mod resolver;
mod server;
mod utils;

use server::serve;

use clap::{Parser, Subcommand};
use config::Settings;
use std::io;
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
    /// Print configuration in json format
    Config {
        /// Print configuration and exit
        #[arg(long, short = 'C', value_name = "FILE")]
        conf: Option<PathBuf>,
    },
    /// Run server
    Serve {
        #[arg(long, short = 'C', value_name = "FILE")]
        conf: Option<PathBuf>,
    },
}

#[actix_web::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Cli::parse();

    const CONF_ENV: &str = "QJAZZ_CONFIG_JSON";

    match &args.command {
        Some(Commands::Config { conf }) => {
            let settings = match conf {
                Some(conf) => Settings::from_file_template(conf)?,
                None => Settings::from_env(CONF_ENV)?,
            };
            serde_json::to_writer_pretty(io::stdout().lock(), &settings)?;
        }
        Some(Commands::Serve { conf }) => {
            let settings = match conf {
                Some(conf) => Settings::from_file_template(conf)?,
                None => Settings::from_env(CONF_ENV)?,
            };
            settings.init_logger();
            serve(settings).await?;
        }
        None => (),
    }
    Ok(())
}

const CLAP_STYLE: clap::builder::styling::Styles = clap::builder::styling::Styles::plain();
