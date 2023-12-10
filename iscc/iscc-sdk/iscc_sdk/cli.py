from pydantic import BaseModel
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import os
import subprocess
from datetime import datetime, timezone
import json, jwt
import base58, base64
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Iterator, Optional, Tuple
from loguru import logger as log
import typer
from pathlib import Path
import iscc_core as ic
import iscc_sdk as idk
from rich.console import Console
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    DownloadColumn,
)
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from datetime import datetime
import rfc3161ng
import requests
from PIL import Image
import hashlib
from io import BytesIO

console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=True)

def get_timestamp(data):

    # Hash the file data
    hasher = hashes.Hash(hashes.SHA512(), default_backend())
    hasher.update(base64.urlsafe_b64decode(data))
    hash_value = hasher.finalize()

    rt = rfc3161ng.RemoteTimestamper('https://freetsa.org/tsr')
    tst = rt.timestamp(data=data)
    # print(rfc3161ng.get_timestamp(tst))

    return tst

def get_timestamp_response(timestamp_request):
    headers = {
        'Content-Type': 'application/timestamp-query'
    }

    try:
        response = requests.post('https://freetsa.org/tsr', data=timestamp_request, headers=headers)
        response.raise_for_status()

        print(f"Timestamp response received successfully")
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Error getting timestamp response: {e}")


def _log_formatter(record: dict) -> str:  # pragma: no cover
    """Log message formatter"""
    color_map = {
        "TRACE": "blue",
        "DEBUG": "cyan",
        "INFO": "bold",
        "SUCCESS": "bold green",
        "WARNING": "yellow",
        "ERROR": "bold red",
        "CRITICAL": "bold white on red",
    }
    lvl_color = color_map.get(record["level"].name, "cyan")
    return (
        "[not bold green]{time:YYYY/MM/DD HH:mm:ss}[/not bold green] | {module:<12} | {line:<3} | {level.icon}"
        + f"  - [{lvl_color}]{{message}}[/{lvl_color}]"
    )


log.add(console.print, level="DEBUG", format=_log_formatter, colorize=True)


def iter_unprocessed(path, root_path=None):
    # type: (str|Path, Optional[str|Path]) -> Iterator[Tuple[Path, int]]
    """
    Walk directory tree recursively with deterministic ordering and yield tuples of file metadata.

    Metadata = (relpath, size)

    - path: pathlib.Path object
    - size: integer file size in number of bytes

    File-entries are yielded in reproducible and deterministic order (bottom-up). Symlink and
    processed files are ignored silently.

    Implementation Note: We use os.scandir to reduce the number of syscalls for metadata collection.
    """
    root_path = Path(root_path or path)
    with os.scandir(path) as entries:
        # Sort the entries
        sorted_entries = sorted(entries, key=lambda e: e.name)

        # Separate directories and files
        dirs = [entry for entry in sorted_entries if entry.is_dir()]
        files = [entry for entry in sorted_entries if entry.is_file()]

        # Recursively process directories first (bottom-up traversal)
        for dir_entry in dirs:
            yield from iter_unprocessed(Path(dir_entry.path), root_path=root_path)

        # Process files in the current directory
        for file_entry in files:
            file_path = Path(file_entry)
            # Ignore result files
            if file_path.name.endswith(".iscc.json") or file_path.name.endswith(".iscc.mp7sig"):
                continue
            # Ignore files that have results
            if Path(file_path.as_posix() + ".iscc.json").exists():
                continue
            file_size = file_entry.stat().st_size
            yield file_path, file_size


def process_file(fp: Path):
    idk.sdk_opts.video_store_mp7sig = True
    try:
        return fp, idk.code_iscc(fp.as_posix())
    except Exception as e:
        return fp, e

def generate_and_store_key(file_path):
    # Generate an ECDSA key pair using the P-256 curve
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # Serialize the private key to PEM format
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Write the private key to the specified file
    with open(file_path, 'wb') as key_file:
        key_file.write(private_key_pem)

    print(f"ECDSA key successfully generated and stored in {file_path}")

def load_key(file_path):
    # Read the private key from the specified file
    with open(file_path, 'rb') as key_file:
        private_key_pem = key_file.read()

    # Deserialize the private key
    private_key = serialization.load_pem_private_key(
        private_key_pem,
        password=None,
        backend=default_backend()
    )

    # print(f"ECDSA key successfully loaded from {file_path}")
    return private_key

def base64url_encode(data):
    # Custom base64url encoding function
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def create_did_key(public_key):
    # Serialize the public key to JWK format
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": base64url_encode(public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )[:32]),
        "y": base64url_encode(public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )[32:])
    }

    # Serialize the JWK to a JSON string with double quotes
    jwk_json = json.dumps(jwk, separators=(',', ':'), sort_keys=True)
    # print(jwk_json)

    # Encode the JWK JSON string using UTF-8
    encoded_jwk = bytes.fromhex('d1d603') + jwk_json.encode('utf-8')

    # Encode the JWK JSON string in base58btc format
    did_key = 'did:key:z' + base58.b58encode(encoded_jwk).decode()

    return did_key


def sign(header, payload, private_key):
    """
    Sign a JSON

    Args:
    - header (dict): JWS header.
    - payload (dict): JWS payload.
    - private_key_path (str): Path to the private key file in PEM format.

    Returns:
    - str: Encoded JWT.
    """
    # Encode the JWT
    jws = jwt.encode(payload, private_key, algorithm="ES256", headers=header)
    return jws

@app.command()
def imagetranspose(file: Path):
    try:
        # Load the image from the file path
        with Image.open(file) as img:
            # Perform the specified transformation
            rotated_img = idk.image.image_exif_transpose(img)

            print(rotated_img.tobytes()[:64].hex())
            # Compute SHA256 hash of the rotated image
            sha256_hash = hashlib.sha256(rotated_img.tobytes()).hexdigest()

            # Print the hash
            print("SHA256 Hash:", sha256_hash)

    except Exception as e:
        print(f"Error: {e}")

@app.command()
def createkey(file: Path):
    """Create private/public key pair and store to the defined path (e.g., key.pem)"""
    generate_and_store_key(file)

@app.command()
def loadKey(file: Path):
    key = load_key(file)
    print(create_did_key(key.public_key()))

@app.command()
def create(file: Path):
    """Create ISCC-CODE for single FILE."""
    log.remove()
    if file.is_file() and file.exists():
        result = idk.code_iscc(file.as_posix())
        typer.echo(result.json(indent=2))
    else:
        typer.echo(f"Invalid file path {file}")
        raise typer.Exit(code=1)


@app.command()
def batch(folder: Path, workers: int = os.cpu_count()):  # pragma: no cover
    """Create ISCC-CODEs for files in FOLDER (parallel & recursive)."""
    if not folder.is_dir() or not folder.exists():
        typer.echo(f"Invalid folder {folder}")
        raise typer.Exit(1)

    file_paths = []
    file_sizes = []
    for path, size in iter_unprocessed(folder):
        file_paths.append(path)
        file_sizes.append(size)

    file_sizes_dict = {path: size for path, size in zip(file_paths, file_sizes)}
    total_size = sum(file_sizes)
    progress = Progress(
        TextColumn("[bold blue]Processing {task.fields[dirname]}", justify="right"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console,
    )

    with progress:
        task_id = progress.add_task("Processing", dirname=folder.name, total=total_size)
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_file, fp) for fp in file_paths]
            for future in as_completed(futures):
                fp, iscc_meta = future.result()
                if isinstance(iscc_meta, idk.IsccMeta):
                    out_path = Path(fp.as_posix() + ".iscc.json")
                    with out_path.open(mode="wt", encoding="utf-8") as outf:
                        outf.write(iscc_meta.json(indent=2))
                    log.info(f"Finished {fp.name}")
                else:
                    log.error(f"Failed {fp.name}: {iscc_meta}")
                progress.update(task_id, advance=file_sizes_dict[fp], refresh=True)


@app.command()
def install():
    """Install content processing tools."""
    idk.install()


@app.command()
def selftest():
    """Run conformance tests."""
    ic.conformance_selftest()

def remove_null_values(input_dict):
    return {key: value for key, value in input_dict.items() if value is not None}

@app.command()
def cs(key_path, file: Path):
    """Create signed ISCC metadata for single FILE."""
    log.remove()
    key = load_key(key_path)
    # print("[*] Private key is loaded")
    did = create_did_key(key.public_key())
    # print("[*] DID:", did)
    if file.is_file() and file.exists():
        result = idk.code_iscc(file.as_posix())
        result2 = vars(result)
        iscc_id = ic.gen_iscc_id(result.iscc, 0, did, 0)['iscc']
        result2["iscc_id"] = iscc_id
        #print("[*] ISCC ID:", iscc_id)
        result2["wallet"] = did
        result2 = remove_null_values(result2)
        # sign JWS
        timestampRaw = datetime.utcnow()
        timestamp = timestampRaw.replace(microsecond=0, tzinfo=timezone.utc).isoformat()
        header = {"sigT": timestamp, "typ": "dades-z", "kid": did, "crit": ["sigT"], "cty": "ld+json"}
        signedMetadata = sign(header, result2, key)
        file_name = str(file) + '.metadata.' + timestampRaw.strftime("%Y-%m-%dT%H-%M-%SZ") + '.jws'
        with open(file_name, 'w') as file:
            file.write(signedMetadata)
        #print("Signed metadata is stored to", file_name)
        print(signedMetadata)
    else:
        typer.echo(f"Invalid file path {file}")
        raise typer.Exit(code=1)

manifestTemplate = {
    "ta_url": "http://timestamp.digicert.com",
    "claim_generator": "CAI_Demo/0.1",
    "private_key": "./keystore/private3.key",
    "sign_cert": "./keystore/certs3.pem",
    "alg": "ES256",
    
    "assertions": [
  ]
}

def execute_external_service(command):
    try:
        # Run the external service command and capture the output
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        # Print the output of the external service
        # print("External service output:", result.stdout)

        # Return the output
        return result.stdout
    except subprocess.CalledProcessError as e:
        # Handle errors if the external service command fails
        print("Error executing external service:", e)
        return None

def add_c2pa_extension(file_path):
    path_obj = Path(file_path)
    # Get the file name without extension
    file_stem = path_obj.stem
    # Get the file extension
    file_suffix = path_obj.suffix
    # Add ".c2pa" before the file extension
    new_file_name = f"{file_stem}.c2pa{file_suffix}"
    # Create the new path with the modified file name
    new_path = path_obj.with_name(new_file_name)
    return new_path

def add_extension(file_path, extension):
    path_obj = Path(file_path)
    # Get the file name without extension
    file_stem = path_obj.stem
    # Get the file extension
    file_suffix = path_obj.suffix
    # Add ".c2pa" before the file extension
    new_file_name = f"{file_stem}.{extension}{file_suffix}"
    # Create the new path with the modified file name
    new_path = path_obj.with_name(new_file_name)
    return new_path

def replace_extension(file_path, extension):
    path_obj = Path(file_path)
    # Get the file name without extension
    file_stem = path_obj.stem
    # Get the file extension
    file_suffix = path_obj.suffix
    # Add ".c2pa" before the file extension
    new_file_name = f"{file_stem}.{extension}"
    # Create the new path with the modified file name
    new_path = path_obj.with_name(new_file_name)
    return new_path

def load_manifest(file_path):
    with open(file_path, 'r') as file:
        json_data = json.load(file)
    return json_data

def load_json(file_path):
    with open(file_path, 'r') as file:
        json_data = json.load(file)
    return json_data

def create_iscc_metadata(file: Path, did: str):
    """Compute the ISCC metadata for a single local file"""
    iscc_metadata_raw = idk.code_iscc(file.as_posix())
    iscc_metadata = vars(iscc_metadata_raw)
    iscc_id = ic.gen_iscc_id(iscc_metadata_raw.iscc, 0, did, 0)['iscc']
    iscc_metadata["iscc_id"] = iscc_id
    #print("[*] ISCC ID:", iscc_id)
    iscc_metadata["wallet"] = did
    return remove_null_values(iscc_metadata)

def sign_iscc_metadata(metadata, with_timestamp: bool, key, did):
    """Sign the ISCC metadata"""
    header = {}
    timestamp_str = ""
    if with_timestamp:
        # TODO: fix the b64 encoding issue
        encoded_payload = jwt.encode(metadata, key='', algorithm=None).split('.')[1]
        tst = get_timestamp(encoded_payload)
        tst_str = rfc3161ng.get_timestamp(tst)
        tst_enc = base64.b64encode(tst)
        # print("[*] Timestamp obtained")
        timestamp_str = tst_str.strftime("%Y-%m-%dT%H:%M:%SZ")
        header = {"sigT": timestamp_str, "tst": tst_enc.decode('utf-8'), "typ": "dades-z", "kid": did, "crit": ["sigT"], "cty": "ld+json"}
    else:
        timestamp_raw = datetime.utcnow()
        timestamp_str = timestamp_raw.replace(microsecond=0, tzinfo=timezone.utc).isoformat()
        header = {"sigT": timestamp_str, "typ": "dades-z", "kid": did, "crit": ["sigT"], "cty": "ld+json"}
    return sign(header, metadata, key), timestamp_str.replace(":", "-")

def create_c2pa_manifest(file: Path, iscc_metadata, signed_metadata, _manifest):
    manifest = _manifest
    # create c2pa manifest with ISCC Metadata
    c2pa_assertion = {
        "label": "ISCC Metadata",
        "data": {
            "metadata": signed_metadata,
            "iscc": iscc_metadata["iscc"]
        },
        "kind": "Json"
    }

    # TODO: for some reason .append extends the manifest globally
    manifest["assertions"] = [c2pa_assertion]
    manifest_str = json.dumps(manifest)

    cmd = ["c2patool", str(file), '--config', manifest_str, "--output", str(add_extension(file, 'c2pa')), "-f", "-s"]
    return execute_external_service(cmd)

@app.command()
def c2pa(manifest_path, file: Path):
    """Create signed ISCC metadata for single FILE."""
    # Load the manifest
    manifest = load_manifest(manifest_path)
    print("[*] C2PA manifest is loaded")

    # Load the keys
    key = load_key(manifest["private_key"])
    print("[*] Private key is loaded")

    # Derive the DID
    did = create_did_key(key.public_key())
    print("[*] DID:", did)


    log.remove()
    if file.is_file() and file.exists():
        iscc_metadata = create_iscc_metadata(file, did)
        signed_metadata, timestamp_str = sign_iscc_metadata(iscc_metadata, False, key, did)
        c2pa_manifest = create_c2pa_manifest(file, iscc_metadata, signed_metadata, manifest)

        output_name = str(file) + '.declaration.' + timestamp_str + '.json'

        # Load the c2pa
        with open(replace_extension(add_extension(file, 'c2pa'), 'c2pa'), 'rb') as file:
            file_content = file.read()
        
        # Encode file content to base64
        c2pa_base64_encoded = base64.b64encode(file_content)
        
        # Convert bytes to string
        c2pa_base64_string = c2pa_base64_encoded.decode('utf-8')

        # store the metadata
        print(file)
        declaration = {
            "iscc": iscc_metadata["iscc"],
            "iscc_metadata": signed_metadata,
            "c2pa_manifest": json.loads(c2pa_manifest),
            "c2pa_raw": c2pa_base64_string
        }

        with open(output_name, 'w') as json_file:
            json.dump(declaration, json_file, indent=2)
        print("[*] Result stored to:", output_name)
    else:
        typer.echo(f"Invalid file path {file}")
        raise typer.Exit(code=1)

# Global config for batch processing
config = {
    "did": "",
    "key": None,
    "with_timestamp": False,
    "manifest": None
}

def process_file_c2pa(fp: Path):
    idk.sdk_opts.video_store_mp7sig = True
    try:
        iscc_metadata = create_iscc_metadata(fp, config["did"])
        signed_metadata, timestamp_str = sign_iscc_metadata(iscc_metadata, config["with_timestamp"], config["key"], config["did"])
        c2pa_manifest = create_c2pa_manifest(fp, iscc_metadata, signed_metadata, config["manifest"])

        # store the metadata
        declaration = {
            "iscc": iscc_metadata["iscc"],
            "iscc_metadata": signed_metadata,
            "c2pa_manifest": json.loads(c2pa_manifest)
        }
        return fp, True, declaration
    except Exception as e:
        return fp, False, e

@app.command()
def c2pabatch(manifest_path, folder: Path, workers: int = os.cpu_count()):  # pragma: no cover
    """Create ISCC-CODEs for files in FOLDER (parallel & recursive)."""
    if not folder.is_dir() or not folder.exists():
        typer.echo(f"Invalid folder {folder}")
        raise typer.Exit(1)

    # Load the manifest
    manifest = load_manifest(manifest_path)
    print("[*] C2PA manifest is loaded")

    # Load the keys
    key = load_key(manifest["private_key"])
    print("[*] Private key is loaded")

    # Derive the DID
    did = create_did_key(key.public_key())
    print("[*] DID:", did)

    global config
    config = {
        "did": did,
        "key": key,
        "with_timestamp": False,
        "manifest": manifest
    }

    file_paths = []
    file_sizes = []
    for path, size in iter_unprocessed(folder):
        file_paths.append(path)
        file_sizes.append(size)

    file_sizes_dict = {path: size for path, size in zip(file_paths, file_sizes)}
    total_size = sum(file_sizes)
    progress = Progress(
        TextColumn("[bold blue]Processing {task.fields[dirname]}", justify="right"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console,
    )

    with progress:
        task_id = progress.add_task("Processing", dirname=folder.name, total=total_size)
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_file_c2pa, fp) for fp in file_paths]
            for future in as_completed(futures):
                fp, success, result = future.result()
                if success:
                    log.info(f"Finished {fp.name}")
                    out_path = Path(fp.as_posix() + ".iscc.json")
                    with open(out_path, 'w') as json_file:
                        json.dump(result, json_file, indent=2)
                    log.info(f"Finished {fp.name}")
                else:
                    log.error(f"Failed {fp.name}: {result}")
                progress.update(task_id, advance=file_sizes_dict[fp], refresh=True)

@app.command()
def cstst(key_path, file: Path):
    """Create signed and timestamped ISCC metadata for single FILE."""
    log.remove()
    key = load_key(key_path)
    # print("[*] Private key is loaded")
    did = create_did_key(key.public_key())
    print("[*] DID:", did)
    if file.is_file() and file.exists():
        result = idk.code_iscc(file.as_posix())
        result2 = vars(result)
        iscc_id = ic.gen_iscc_id(result.iscc, 0, did, 0)['iscc']
        result2["iscc_id"] = iscc_id
        print("[*] ISCC ID:", iscc_id)
        print("[*] ISCC code:", result2['iscc'])
        result2["wallet"] = did
        result2 = remove_null_values(result2)
        # sign JWS
        encoded_payload = jwt.encode(result2, key='', algorithm=None).split('.')[1]
        tst = get_timestamp(encoded_payload)
        tst_str = rfc3161ng.get_timestamp(tst)
        tst_enc = base64.b64encode(tst)
        print("[*] Timestamp obtained")
        header = {"sigT": tst_str.strftime("%Y-%m-%dT%H:%M:%SZ"), "tst": tst_enc.decode('utf-8'), "typ": "dades-z", "kid": did, "crit": ["sigT"], "cty": "ld+json"}
        signedMetadata = sign(header, result2, key)
        file_name = str(file) + '.metadata+timestamp.' + tst_str.strftime("%Y-%m-%dT%H-%M-%SZ") + '.jws'
        with open(file_name, 'w') as file:
            file.write(signedMetadata)
        print("Signed metadata is stored to", file_name)
    else:
        typer.echo(f"Invalid file path {file}")
        raise typer.Exit(code=1)

@app.command()
def register(config_path: Path, manifest_path: Path):
    """Register the ISCC metadata to an ISCC registry"""

    # Load the config
    config = load_json(config_path)
    manifest = load_json(manifest_path)

    headers = {
    'accept': 'application/json',
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + config["access_token"],
    }
    print(headers)
    timestamp_raw = datetime.utcnow()
    timestamp_str = timestamp_raw.replace(microsecond=0, tzinfo=timezone.utc).isoformat()

    data = {
        "timestamp": timestamp_str,
        "chain_id": 0,
        "block_height": 0,
        "block_hash": "",
        "tx_idx": 0,
        "tx_hash": "",
        "declarer": "local",
        "iscc_code": manifest["iscc"],
        "message": json.dumps(manifest),
        "meta_url": "http://",
        "registrar": "local"
    }

    url = config['endpoint']+'/api/v1/register'
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
        print("Request successful. Status code:", response.status_code)
        print("Response:", response.json())
    except requests.exceptions.RequestException as e:
        print("Error:", e)

@app.command()
def timestamp():
    """Test the timestamping service: freetsa.org"""
    rt = rfc3161ng.RemoteTimestamper('https://freetsa.org/tsr')
    tst = rt.timestamp(data=b'Alice')
    print(rfc3161ng.get_timestamp(tst))



# Get the number of available CPUs
num_cpus = os.cpu_count()

app2 = FastAPI()

def process_image(base64_image):
    # Replace this function with your actual image processing logic
    # For example, decode base64, perform processing, and return result
    decoded_image = base64.b64decode(base64_image)
    # ... Your image processing logic here ...
    processed_result = f"Processed: {len(decoded_image)} bytes"
    return processed_result

def base64_to_image(base64_string):
    # Remove the base64 prefix if present
    if base64_string.startswith('data:image'):
        base64_string = base64_string.split(',')[-1]

    # Decode the base64 string
    image_data = base64.b64decode(base64_string)

    # Create an in-memory file-like object
    image_io = BytesIO(image_data)

    # Open the image using Pillow (PIL)
    image = Image.open(image_io)

    return image

def bytes_to_image(image_io):
    # Open the image using Pillow (PIL)
    image = Image.open(image_io)

    return image

def base64_to_stream(base64_string):
    # Remove the base64 prefix if present
    if base64_string.startswith('data:image'):
        base64_string = base64_string.split(',')[-1]

    # Decode the base64 string
    image_data = base64.b64decode(base64_string)

    # Create an in-memory file-like object
    return BytesIO(image_data)

class Request(BaseModel):
    image: str

class Response(BaseModel):
    iscc: str

@app2.post('/metadata')
async def process_image_route(request: Request):
    try:
        img = base64_to_image(request.image)
        meta = dict()
        pixels = idk.image_normalize(img)
        code_obj = ic.gen_image_code_v0(pixels, bits=idk.core_opts.image_bits)
        meta.update(code_obj)

        code = idk.IsccMeta.construct(**meta)
        return Response(iscc=code.iscc)

    except Exception as e:
        return JSONResponse(content={'error': str(e)}, status_code=500)

@app2.post('/v2/iscc')
async def process_v2_iscc(request: Request):
    try:
        # def code_iscc_v2(stream):
        # type: (bytes) -> idk.IsccMeta
        """
        Generate ISCC-CODE.

        The ISCC-CODE is a composite of Meta, Content, Data and Instance Codes.

        :param str fp: Filepath used for ISCC-CODE creation.
        :return: ISCC metadata including ISCC-CODE and merged metadata from ISCC-UNITs.
        :rtype: IsccMeta
        """

        stream = base64_to_stream(request.image)

        # Generate ISCC-UNITs in parallel
        with ThreadPoolExecutor() as executor:
            instance = executor.submit(code_instance_v2, stream)
            data = executor.submit(code_data_v2, stream)
            content = executor.submit(code_content_v2, stream)
        # instance = code_instance_v2(stream)
        # print("instance")
        # data = code_data_v2(stream)
        # print("data")
        # content = code_content_v2(stream)
        # print("content")

        # Wait for all futures to complete and retrieve their results
        instance, data, content = (
            instance.result(),
            data.result(),
            content.result()
        )

        # Compose ISCC-CODE
        iscc_code = ic.gen_iscc_code_v0([content.iscc, data.iscc, instance.iscc])
        print(iscc_code)
        print(type(iscc_code))

        # Merge ISCC Metadata
        # iscc_meta = dict()
        # iscc_meta.update(instance.dict())
        # iscc_meta.update(data.dict())
        # iscc_meta.update(content.dict())
        # iscc_meta.update(iscc_code)

        return Response(iscc=iscc_code["iscc"])

    except Exception as e:
        print('eee', e)
        return JSONResponse(content={'error': str(e)}, status_code=500)
    

@app2.post('/v1/iscc')
async def iscc_v1(request: Request):
    try:
        # Get the base64-encoded image from the request
        base64_image = request.image

        # Decode base64 image
        image_data = base64.b64decode(base64_image)

        # Calculate SHA-256 hash of the image
        sha256_digest = hashlib.sha256(image_data).hexdigest()

        # Specify the folder where you want to save the image
        save_folder = "images"

        # Create the folder if it doesn't exist
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)

        # Generate the filename based on the SHA-256 hash
        filename = os.path.join(save_folder, f"{sha256_digest}.png")

        # Save the image to the specified folder
        with open(filename, "wb") as f:
            f.write(image_data)

        cmd = ["idk", "create", filename]
        metadata = json.loads(execute_external_service(cmd))
        # print(metadata)
        return Response(iscc=metadata['iscc'])

    except Exception as e:
        return JSONResponse(content={'error': str(e)}, status_code=500)

def code_content_v2(stream):
    img = bytes_to_image(stream)
    pixels = idk.image_normalize(img)
    meta = ic.gen_image_code_v0(pixels, bits=idk.core_opts.image_bits)
    
    return idk.IsccMeta.construct(**meta)

## updated methods
def code_instance_v2(stream):
    # type: (byte) -> idk.IsccMeta
    """
    Create ISCC Instance-Code.

    The Instance-Code is prefix of a cryptographic hash (blake3) of the input data.
    It´s purpose is to serve as a checksum that detects even minimal changes
    to the data of the referenced media asset. For cryptographicaly secure integrity
    checking a full 256-bit multihash is provided with the `datahash` field.

    :param str fp: Filepath used for Instance-Code creation.
    :return: ISCC metadata including Instance-Code, datahash and filesize.
    :rtype: IsccMeta
    """

    # Now, 'stream' can be used as a file-like object
    meta = ic.gen_instance_code_v0(stream, bits=idk.core_opts.instance_bits)
    return idk.IsccMeta.construct(**meta)

def code_data_v2(stream):
    # type: (str) -> idk.IsccMeta
    """
    Create ISCC Data-Code.

    The Data-Code is a similarity preserving hash of the input data.

    :param str fp: Filepath used for Data-Code creation.
    :return: ISCC metadata including Data-Code.
    :rtype: IsccMeta
    """

    # Now, 'stream' can be used as a file-like object
    meta = ic.gen_data_code_v0(stream, bits=idk.core_opts.data_bits)

    return idk.IsccMeta.construct(**meta)


@app.command()
def api(_port):
    uvicorn.run("idk:app2", port=_port, host='127.0.0.1')

if __name__ == "__main__":  # pragma: no cover
    app()
