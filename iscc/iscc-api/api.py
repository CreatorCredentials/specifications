"""ISCC API
Version: 0.1
"""
import argparse
import hashlib
import json
import os

from urllib.parse import urljoin, urlencode, urlunparse
from dotenv import load_dotenv
from typing import List
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import asyncio
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Form, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from mpmath import mp
from PIL import Image, ImageEnhance
from pydantic import BaseModel
import aiohttp
import iscc_core as ic
import iscc_sdk as idk


# Variables
IMG_PATH = ""
DECIMAL_PLACES = 20
DB_URL = ""

# Init
app = FastAPI()
mp.dps = DECIMAL_PLACES


# Class definitions
class Response(BaseModel):
    """
    /v3/iscc endpoint response
    """

    iscc: str


class ExplainRequest(BaseModel):
    """
    /v2/explain endpoint request
    """

    iscc: str


class ExplainResponse(BaseModel):
    """
    /v2/explain endpoint response
    """

    readable: str
    iscc: str
    hex: str
    log: str


# Methods
def load_env_file():
    """Load .env from current or parent directory"""
    # Try loading from the current directory
    dotenv_path = os.path.join(os.getcwd(), ".env")

    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        print(f"Environment variables loaded from {dotenv_path}")
        return

    # Try loading from the parent directory
    parent_dir = os.path.abspath(os.path.join(os.getcwd(), os.pardir))
    dotenv_path_parent = os.path.join(parent_dir, ".env")

    if os.path.exists(dotenv_path_parent):
        load_dotenv(dotenv_path_parent)
        print(f"Environment variables loaded from {dotenv_path_parent}")
    else:
        print("No .env file found in the current or parent directory")


def bytes_to_image(image_io):
    # Open the image using Pillow (PIL)
    image = Image.open(image_io)

    return image


def code_content_v2(stream: BytesIO):
    """Compute Code Content

    Args:
        stream (_type_): _description_

    Returns:
        _type_: _description_
    """
    img = bytes_to_image(stream)
    pixels = idk.image_normalize(img)
    meta = ic.gen_image_code_v0(pixels, bits=idk.core_opts.image_bits)
    print("meta", meta)

    return idk.IsccMeta.construct(**meta)


def code_data_v2(stream: BytesIO):
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


def code_instance_v2(stream: BytesIO):
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


async def post_iscc(db_url: str,
    iscc: str, content: str, data: str, instance: str, site_url: str, digest: str, image_data
):
    """
    Store information in a local DB
    """
    # Store the thumbnail
    IMG_PATH = get_required_env_variable("ISCC_DIR")
    output_path = IMG_PATH + "/" + iscc + ".jpg"
    if not os.path.exists(output_path):
        # Create an in-memory file-like object
        image_io = BytesIO(image_data)
        # Open the image using Pillow (PIL)
        image = Image.open(image_io)

        image.thumbnail((128, 128), resample=idk.LANCZOS)
        # Enhance sharpness
        enhanced_img = ImageEnhance.Sharpness(image.convert("RGB")).enhance(1.4)

        # Save the processed image
        enhanced_img.save(output_path)
        print("Image saved")

    # store to DB
    content_code = ic.Code(content)
    content_uint = content_code.hash_uint
    c_hex = content_code.hash_hex
    c_log = mp.nstr(mp.log10(content_uint), n=DECIMAL_PLACES)

    data_code = ic.Code(data)
    data_uint = data_code.hash_uint
    d_hex = data_code.hash_hex
    d_log = mp.nstr(mp.log10(data_uint), n=DECIMAL_PLACES)

    instance_code = ic.Code(instance)
    instance_uint = instance_code.hash_uint
    i_hex = instance_code.hash_hex
    i_log = mp.nstr(mp.log10(instance_uint), n=DECIMAL_PLACES)

    # store to DB
    headers = {"Content-Type": "application/json"}
    data = {
        "iscc": iscc,
        "hash": digest,
        "instance-code-hex": i_hex,
        "content-code-hex": c_hex,
        "data-code-hex": d_hex,
        "instance-code-log": i_log,
        "content-code-log": c_log,
        "data-code-log": d_log,
        "source": site_url,
    }

    print(data)

    async with aiohttp.ClientSession() as session:
        async with session.post(db_url, data=json.dumps(data), headers=headers) as response:
            if response.status == 201:
                print("Data stored successfully")
            else:
                print(f"Failed to store data. Status code: {response.status}")
                print(await response.text())
    
    await post_c2pa_image(image_data)

async def post_c2pa_image(image_bytes):
    url = 'http://localhost:8001/v1/c2pa'

    headers = {
        'Content-Type': 'image/png',
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=image_bytes) as response:
            # Check the response
            if response.status == 200:
                print('POST request successful')
                print('Response:', await response.text())
            else:
                print(f'POST request failed with status code {response.status}')
                print('Response:', await response.text())


def create_directory_if_not_exists(directory_path):
    try:
        path = Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating directory: {e}")
        raise


@app.post("/v2/explain")
async def explain(request: ExplainRequest):
    """Decode the ISCC code

    Args:
        request (ExplainRequest): _description_

    Returns:
        _type_: _description_
    """
    try:
        norm = ic.iscc_normalize(request.iscc)
        decomposed = ic.iscc_decompose(norm)
        results = []
        for unit in decomposed:
            code = ic.Code(unit)
            readable = code.explain
            data = code.hash_uint
            d_hex = code.hash_hex
            d_log = mp.nstr(mp.log10(data), n=DECIMAL_PLACES)

            result = ExplainResponse(readable=readable, iscc=code.code, hex=d_hex, log=d_log)
            results.append(jsonable_encoder(result))

        return JSONResponse(content=results, status_code=200)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

async def get_iscc_by_digest(digest: str):
    schema = get_required_env_variable("REGISTRY_SCHEMA")
    hostname = get_required_env_variable("REGISTRY_HOST_PORT")
    endpoint = get_required_env_variable("REGISTRY_API_RECORDS")
    url_components = (schema, hostname, endpoint,'', urlencode({'digest': digest})  ,'')
    url = urlunparse(url_components)

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()


@app.post("/v3/iscc")
async def process_v3_iscc(url: str = Form(...), image: UploadFile = None):
    """
    Generate ISCC-CODE.
    """
    schema = get_required_env_variable("STORAGE_SCHEMA")
    hostname = get_required_env_variable("STORAGE_HOST_PORT")
    endpoint = get_required_env_variable("STORAGE_API_POST_STORE")
    db_url = urljoin(f"{schema}://{hostname}/", endpoint)

    try:
        print(url)
        # Read the image file as bytes
        image_bytes = await image.read()

        image_data = image_bytes
        digest = hashlib.sha256(image_data).hexdigest()
        print(digest)

        # Try fetching data
        result = await get_iscc_by_digest(digest)
        # Check if the fetch was successful
        if result is not None:
            r = json.loads(result)
            if 'data' in r:
                return Response(iscc=r['data']["iscc"])

        stream = BytesIO(image_data)
        site_url = url

        # Generate ISCC-UNITs in parallel
        with ThreadPoolExecutor() as executor:
            instance = executor.submit(code_instance_v2, stream)
            data = executor.submit(code_data_v2, stream)
            content = executor.submit(code_content_v2, stream)

        # Wait for all futures to complete and retrieve their results
        instance, data, content = (instance.result(), data.result(), content.result())

        # Compose ISCC-CODE
        arg: List[str] = [content.iscc, data.iscc, instance.iscc]
        iscc_code = ic.gen_iscc_code_v0(arg)

        task = asyncio.create_task(
            post_iscc(
                db_url,
                iscc_code["iscc"],
                content.iscc,
                data.iscc,
                instance.iscc,
                site_url,
                digest,
                image_data,
            )
        )

        return Response(iscc=iscc_code["iscc"])

    except Exception as e:
        print("Error", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

    finally:
        # Ensure background task completes even if there was an exception
        if "task" in locals():
            try:
                await task  # Wait for the background task to finish
            except Exception as e:
                print("Error in background task", e)

def get_required_env_variable(variable_name):
    value = os.getenv(variable_name)
    if value is None:
        raise ValueError(f"Environment variable {variable_name} is not set.")
    return str(value)

def main():
    global DB_URL
    global IMG_PATH
    # Load .env
    load_env_file()

    # Storage API
    schema = get_required_env_variable("STORAGE_SCHEMA")
    hostname = get_required_env_variable("STORAGE_HOST_PORT")
    endpoint = get_required_env_variable("STORAGE_API_POST_STORE")
    DB_URL = urljoin(f"{schema}://{hostname}/", endpoint)

    # Thumbnail Path
    IMG_PATH = get_required_env_variable("ISCC_DIR")

    # ISCC host and port
    iscc_host = get_required_env_variable("ISCC_HOST")
    iscc_port = get_required_env_variable("ISCC_PORT")

    parser = argparse.ArgumentParser(description="ISCC API v0.1")
    # Add command-line arguments
    parser.add_argument("--path", type=str, default=IMG_PATH, help="Path to static file store")
    parser.add_argument("--port", type=int, default=iscc_port, help="ISCC API port number")
    parser.add_argument("--host", type=str, default=iscc_host, help="ISCC host")
    parser.add_argument(
        "--db", type=str, default=DB_URL, help="Local DB URL argument"
    )

    # Parse command-line arguments
    args = parser.parse_args()

    DB_URL = args.db
    IMG_PATH = args.path
    iscc_port = args.port

    # Your script logic using args.path, args.port, and args.db_url
    print("Path:", IMG_PATH)
    print("Port:", args.port)
    print("DB Endpoint:", args.db)

    try:
        create_directory_if_not_exists(IMG_PATH)
    except:
        print("Failed to create the directory.")
        raise

    config = uvicorn.Config("api:app", host=iscc_host, port=iscc_port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()

#  https://search.liccium.app/asset/nns?iscc=ISCC%3AKECRTQNOLG2CAFCMZSHXAMUL7ED6IOMIZYIZ4UYBIBIO5XWUFX4KMWI&mode=image&isMainnet=false