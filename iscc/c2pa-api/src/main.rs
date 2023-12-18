use actix_web::{post, web, App, HttpRequest, HttpResponse, HttpServer};
use bytes::Bytes;
use c2pa::jumbf_io;
use clap::{Arg, Command};
use dotenv::from_filename;
use image::io::Reader as ImageReader;
use sha256::digest;
use std::env;
use std::fs;
use std::io;
use std::path::Path;

#[derive(Clone)]
struct AppState {
    c2pa_store_path: String,
}

#[post("/v1/c2pa")]
async fn handle_post_request(
    data: web::Data<AppState>,
    payload: Bytes,
    _req: HttpRequest,
) -> HttpResponse {
    // Convert Bytes to &[u8]
    let payload_bytes: &[u8] = payload.as_ref();
    // Compute SHA-256 hash
    let hash_result = digest(payload_bytes);
    // Print the SHA-256 hash
    println!("SHA-256 Hash: {}", hash_result);

    let image_bytes: &[u8] = payload_bytes;
    // detect image bytes
    // Store the result in a variable
    let asset_type: String = detect_image_format(&image_bytes);

    let result = jumbf_io::load_jumbf_from_memory(&asset_type, &image_bytes);

    match result {
        Ok(manifest) => {
            let file_name: String = format!("{}/{}.c2pa", data.c2pa_store_path, hash_result);
            let out_path: &Path = Path::new(&file_name);

            // Check if the file exists
            if let Ok(metadata) = fs::metadata(out_path) {
                if metadata.is_file() {
                    // File exists
                    return HttpResponse::Ok().body("OK");
                } else {
                    // Path e, but it's not a file
                    return HttpResponse::InternalServerError()
                        .body("Failed to store the C2PA Manifest.");
                }
            } else {
                match jumbf_io::save_jumbf_to_file(&manifest, out_path, Some(out_path)) {
                    Ok(()) => {
                        return HttpResponse::Ok()
                            .body("Image received and processed successfully!");
                    }
                    Err(_) => {
                        // Return a 500 error
                        return HttpResponse::InternalServerError().body("Internal Server Error");
                    }
                }
            }
        }
        Err(error) => {
            // Print the error message to stdout
            HttpResponse::InternalServerError().body(error.to_string())
        }
    }
}

/// extract binary data from request
#[actix_web::main]
async fn main() -> std::io::Result<()> {
    // Load .env
    from_filename(".env").ok();

    let mut host = env::var("C2PA_HOST_PORT").expect(".env variable C2PA_HOST_PORT not set");
    let mut c2pa_store_path = env::var("C2PA_DIR").expect(".env variable C2PA_DIR not set");

    // If CLI args set, override .env
    let matches = Command::new("c2pa-api")
        .version("0.2.1")
        .author("Alen Horvat")
        .about("C2PA API service")
        .arg(
            Arg::new("URL")
                .short('e')
                .long("endpoint")
                .help("Example: http://localhost:3000")
                .required(false),
        )
        .arg(
            Arg::new("PATH")
                .short('s')
                .long("c2pastore")
                .help("Example: c2pa-store")
                .required(false),
        )
        .get_matches();

    // Check if "URL" argument was passed; override .env value
    if let Some(url_value) = matches.get_one::<String>("URL") {
        host = url_value.clone();
    } else {
        println!("URL argument not passed, using .env value {host}");
    }
    println!("Starting a service at: {host}");

    // Check if "PATH" argument was passed; override .env value
    if let Some(path_value) = matches.get_one::<String>("PATH") {
        c2pa_store_path = path_value.clone();
    } else {
        println!("PATH argument not passed, using .env value {c2pa_store_path}");
    }

    match create_folder_if_not_exists(&c2pa_store_path) {
        Ok(_) => println!("Folder created or already exists."),
        Err(err) => eprintln!("Error: {}", err),
    }
    println!("Storing C2PA Manifests to: {c2pa_store_path}");

    HttpServer::new(move || {
        App::new()
            .app_data(web::PayloadConfig::new(1024 * 1024 * 10)) // 10Mb - max upload size
            .app_data(web::Data::new(AppState {
                c2pa_store_path: c2pa_store_path.clone(),
            }))
            .service(handle_post_request)
    })
    .bind(host)?
    .run()
    .await
}

fn create_folder_if_not_exists(folder_path: &str) -> std::io::Result<()> {
    fs::create_dir_all(folder_path)?;
    Ok(())
}

fn detect_image_format(data: &[u8]) -> String {
    // Create an image reader from the byte data
    let reader = ImageReader::new(io::Cursor::new(data));
    match reader.with_guessed_format()
     {
        Ok(guess) =>  {
            let format = guess.format();
            match format {
                Some(f) => format!("{:?}", f),
                None => String::new()
            }
        },
        Err(_guess) => String::new()
    }
}
