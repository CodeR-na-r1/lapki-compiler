import asyncio
import pytest
from compiler.Client import Client
from aiofile import async_open
import base64
from time import gmtime, strftime
import json
from pathlib import Path
import subprocess

from compiler.config import SERVER_PORT

pytest_plugins = ('pytest_asyncio',)

BASE_ADDR = f'http://localhost:{SERVER_PORT}/ws'

@pytest.mark.asyncio
async def test_sendSmth():
    client = Client()
    await client.doConnect(BASE_ADDR)
    await client.sendSMJson(path='examples/ExampleRequestSM.json')

#deprecated
@pytest.mark.asyncio
async def test_sendSourceFileCpp():
    client = Client()
    await client.doConnect('{BASE_ADDR}/ws/source')
    await client.sendSourceFile(path='examples/MonoFileExample/cpp_example.cpp', compiler="g++", flags=[])
    
    response = await client.getResult()
    
    async with async_open("examples/cpp_example.o", 'rb') as f:
        binary = await f.read()
    
    binary = base64.b64encode(binary)
    binary = binary.decode("ascii")
    
    print(response)    
    assert response == {
        "result" : "OK",
        "compilationCommand" : "g++ cpp_example.cpp -o build/cpp_example.o",
        "returnCode" : 0,
        "stdout" : "",
        "stderr" : "",
        "binary" : {
            "filename": "cpp_example.o",
            "fileContent" : binary 
        }
    }

# Сделать параметрическим

@pytest.mark.asyncio
async def test_sendMultifileProject():
    client = Client()
    await client.doConnect(f'{BASE_ADDR}/source')
    req = await client.sendMultiFileProject("examples/MultifilesExample", "g++", ["-std=c++2a"], ["*.cpp", "*.hpp"])

    result = await client.ws.receive_json()
    result = json.loads(result)
    path = "client/" + strftime('%Y-%m-%d %H:%M:%S', gmtime()) + "/"
    Path(path).mkdir(parents=True)
    for binary in result["binary"]:
        data = binary["fileContent"].encode('ascii')
        data = base64.b64decode(binary["fileContent"])

        async with async_open(path + binary["filename"], "wb") as f:
            await f.write(data)
    
    
    subprocess.run(["chmod", "u+x", path + "a.out"])
    result = subprocess.run(["./" + path + "a.out"], capture_output=True, text=True)
    stdout = result.stdout.replace("\n", '')
    assert stdout == "Result: 8"

@pytest.mark.asyncio
async def test_sendArduino():
    client = Client()
    await client.doConnect(f'{BASE_ADDR}/source')
    req = await client.sendMultiFileProject("examples/ExampleSketch", "arduino-cli", ["-b", "arduino:avr:uno", "ExampleSketch.ino"], ["*.ino"])
    result = await client.ws.receive_json()
    result = json.loads(result)
    path = "client/" + strftime('%Y-%m-%d %H:%M:%S', gmtime()) + "/"
    Path(path).mkdir(parents=True)
    for binary in result["binary"]:
        data = binary["fileContent"].encode('ascii')
        data = base64.b64decode(binary["fileContent"])
        async with async_open(path + binary["filename"], "wb") as f:
            await f.write(data)


@pytest.mark.asyncio
async def test_sendSMJson():
    client = Client()
    await client.doConnect(BASE_ADDR)
    await client.sendSMJson("examples/ExampleRequestSM5.json")
    response = json.loads(await client.ws.receive_json())
    
@pytest.mark.asyncio
async def test_sendNestedSMJson():
    client = Client()
    await client.doConnect(BASE_ADDR)
    await client.sendSMJson("examples/ExampleRequestSMWithChilds.json")
    response = json.loads(await client.ws.receive_json())
    
    
@pytest.mark.asyncio
async def test_sendArduinoSMJson():
    client = Client()
    await client.doConnect(BASE_ADDR)
    await client.sendSMJson("examples/ExampleRequestSMArduino.json")
    response = json.loads(await client.ws.receive_json())
    path = "client/" + strftime('%Y-%m-%d %H:%M:%S', gmtime()) + "/"
    Path(path).mkdir(parents=True)
    for binary in response["binary"]:
        data = binary["fileContent"].encode('ascii')
        data = base64.b64decode(binary["fileContent"])
        async with async_open(path + binary["filename"], "wb") as f:
            await f.write(data)

@pytest.mark.asyncio
async def test_berlogaImport():
    client = Client()
    await client.doConnect(f"{BASE_ADDR}/berloga/import")
    response = await client.sendBerlogaScheme("examples/Autoborder_638213644305392731.graphml")
    path = "client/" + strftime('%Y-%m-%d %H:%M:%S', gmtime()) + "/"
    Path(path).mkdir(parents=True)
    async with async_open(path + "berlogaScheme.json", "w") as f:
        await f.write(response)
    
    await client.ws.close()
