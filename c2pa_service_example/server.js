/**
 * Copyright 2023 Adobe
 * All Rights Reserved.
 *
 * NOTICE: Adobe permits you to use, modify, and distribute this file in
 * accordance with the terms of the Adobe license agreement accompanying
 * it.
 */

var express = require('express');
const fileUpload = require('express-fileupload');
const cors = require('cors');
const fs = require('fs');
const fsPromises = fs.promises;
const bodyParser = require('body-parser');
const morgan = require('morgan');
const path = require('path');
const _ = require('lodash');
const fetch = require('node-fetch');
const util = require('util');
const child = require('child_process')
const jwt = require('jsonwebtoken');

let exec = util.promisify(child.exec);

const manifestFilePath = '../manifest-tmp.json'; // Specify the manifest file path

const port = process.env.PORT || 8000;

function loadManifest(filePath) {
    try {
    // Read the contents of the file
    const fileContent = fs.readFileSync(filePath, 'utf8');

    // Parse the JSON content
    const jsonData = JSON.parse(fileContent);

    return jsonData;
  } catch (error) {
    console.error('Error reading JSON file:', error.message);
    return null;
  }
}

async function writeManifest(dict, fileName) {
  try {
    // Convert the dictionary to JSON string
    const jsonString = JSON.stringify(dict, null, 2); // 2 spaces for indentation

    // Write the JSON string to the local file
    await fsPromises.writeFile(fileName, jsonString);

    console.log(`Data has been written to ${fileName}`);
  } catch (error) {
    console.error('Error writing to file:', error);
  }
}

const manifestPath = "manifest.json"

var manifest = loadManifest(manifestPath)

var app = express();

// serve our web client
app.use(express.static('client'));

// Allow urls from the uploads folder to be served
let imageFolder = 'uploads'
app.use(express.static(imageFolder));

// Create a local folder to hold images in this example.
if(!fs.existsSync(imageFolder)){
  fs.mkdirSync(imageFolder)
}

// Enable files upload.
app.use(fileUpload({
  createParentPath: true,
  limits: { 
      fileSize: 2 * 1024 * 1024 * 1024 // max upload file(s) size
  },
}));

// Add other middleware.
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.raw({type:"image/*",limit:'20mb', extended:true}));
app.use(bodyParser.urlencoded({extended: true}));
app.use(morgan('dev'));

// Runs c2patool to get version info using exec
app.get('/version', async function (req, res) {
  try {
    let result = await exec('./c2patool --version');
    console.log(result);
    res.send(result.stdout);
  } catch (err) {
    res.status(500).send(err);
  }
});

/*
// Uploads a file, adds a C2PA manifest and returns a URL
app.post('/upload', async (req, res) => { 
  try {
    let fileName = req.query.name;
    let filePath = `${imageFolder}/${fileName}`;
    // upload the file
    await fsPromises.appendFile(filePath, Buffer.from(req.body),{flag:'w'});

    // call iscc to get iscc metadata
    let idkCommand = `idk cs iscc-signing-key.pem "${filePath}"`;
    let idkResult = await exec(idkCommand);
    console.log(idkResult);

    assertion = {
    "label": "ISCC Metadata",
    "data": idkResult.stdout,
    "kind": "Json"
    }

    let manifest2 = manifest;
    console.log(manifest2)
    manifest2["assertions"].push(assertion);

    await writeManifest(manifest2, "../manifest-tmp.json");

    // call c2patool to add a manifest
    let command = `./c2patool "${filePath}" -m ../manifest-tmp.json -o "${filePath}" -f`;
    let result = await exec(command);
    // get the manifest store report from stdout
    let report = JSON.parse(result.stdout)
    res.send({
        name: fileName,
        url: `http://localhost:${port}/${fileName}`,
        report
      });
  } catch (err) {
    console.log(err);
    // return errors to the client
    res.status(500).send(err);
  }
});
*/

// Uploads a file, adds a C2PA manifest, and returns a URL
app.post('/upload', async (req, res) => {
    try {
        const fileName = req.query.name;
        const filePath = `${imageFolder}/${fileName}`;

        // Upload the file to the "uploads" folder
        await fsPromises.appendFile(filePath, Buffer.from(req.body), { flag: 'w' });

        // Call iscc to get ISCC metadata
        const idkCommand = `idk cs iscc-signing-key.pem "${filePath}"`;
        const idkResult = await exec(idkCommand);
        // console.log(idkResult);

        // Decode the JWT without verification
        const payload = jwt.decode(idkResult.stdout.replace(/\n/g, ''));
        // console.log(payload)

        const assertion = {
            label: 'ISCC Metadata',
            data: {
              metadata: idkResult.stdout,
              isccCode: payload["iscc"]
            },
            kind: 'Json',
        };

        // Read existing manifest or create a new one
        let manifest;
        try {
            const manifestData = await fsPromises.readFile("manifest.json", 'utf-8');
            manifest = JSON.parse(manifestData);
        } catch (error) {
            manifest = { assertions: [] };
        }

        manifest.assertions.push(assertion);

        // Write updated manifest
        await writeManifest(manifest, manifestFilePath);

        // Call c2patool to add a manifest
        const c2patoolCommand = `./c2patool "${filePath}" -m ${manifestFilePath} -o "${filePath}" -f`;
        const result = await exec(c2patoolCommand);

        // Get the manifest store report from stdout
        const report = JSON.parse(result.stdout);

        res.send({
            name: fileName,
            url: `http://localhost:${port}/${fileName}`,
            urlRelative: `/${fileName}`,
            report,
        });
    } catch (err) {
        console.log(err);
        // Return errors to the client
        res.status(500).send(err);
    }
});


// the default endpoint is test page for this service
app.get('/', function (req, res) {
  res.sendFile(path.join(__dirname, 'client/index.html'));
});

// start the http server
app.listen(port, () => 
  console.log(`CAI HTTP server listening on port ${port}.`)
);

