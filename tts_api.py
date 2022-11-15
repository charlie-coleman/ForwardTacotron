from gen_forward import ForwardGenerator
import flask
from flask_cors import CORS, cross_origin
import uuid
from pathlib import Path
import os
import datetime
import argparse
from api.api_db import API_DB, RequestStatus
import threading
from utils.files import read_config

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config', type=str, default="./api.yaml", help="path to the API config.")

args = parser.parse_args()

config = read_config(args.config)

forward_models_base_path = Path(config['forward_models_base_path'])
wavernn_model_path = Path(config['wavernn_model_path'])
output_path = Path(config['output_path'])
database_path = Path(config['database_path'])

api_base_url = config['api_base_url']
response_base_url = config['response_base_url']

app = flask.Flask(__name__)
cors = CORS(app)
app.config["CORS_HEADERS"] = 'Content-Type'

generators = {}

ttsdb = API_DB(database_path)

def create_generators(config):
  generator_dict = {}
  for line in config['forward_models']:
    try:
      name, filename = line.split(":")
    except:
      print(f"Unable to parse line {line}")
    generator_dict[name] = ForwardGenerator(forward_models_base_path / filename, "wavernn", wavernn_model_path)
  return generator_dict

def api_output(request_id, status):
  location = "" if status != RequestStatus.COMPLETED else f"{response_base_url}{request_id}.wav"
  resp = {
    'id': request_id,
    'timestamp': datetime.datetime.now(),
    'status': status.value,
    'path': location
  }
  return flask.jsonify(resp)

def output_wav_path(request_id):
  return output_path / f'{request_id}.wav'

def generate_tts(request_id, generator, text, vocoder="wavernn"):
  try:
    wav_path = output_wav_path(request_id)
    if (vocoder == "grifflim"):
      generator.generate_grifflim(text, str(wav_path))
    else:
      generator.generate(text, str(wav_path))
    ttsdb.update_request_status(request_id, RequestStatus.COMPLETED)
  except:
    print("Failed to generate TTS output.")
    ttsdb.update_request_status(request_id, RequestStatus.FAILED)

@app.route('/', methods=['GET'])
@cross_origin()
def home():
  return f"""<h1>LusciousLollipop's TTS API.</h1>
             <p>Try <a href="{api_base_url}api/v1/tts?text=Test%201%2C%202%2C%203%2C%204.">this</a></p>"""

@app.route('/api/v1/tts', methods=['GET'])
@cross_origin()
def api_tts():
  if 'model' in flask.request.args:
    model_name = flask.request.args['model']
    text = "Test input because no sentence was provided." if 'text' not in flask.request.args else flask.request.args['text']
    vocoder = "wavernn" if 'voc' not in flask.request.args else flask.request.args['voc']

    # if the model name provided is not in our generators dictionary, return failed
    if model_name not in generators:
      print(f"Could not find model name {model_name} in generators.")
      return api_output("-1", RequestStatus.FAILED)

    if vocoder not in ['wavernn', 'grifflim']:
      vocoder = 'wavernn'
    
    (request_id, status) = ttsdb.add_request(text)
    t1 = threading.Thread(target=generate_tts, args=(request_id, generators[model_name], text, vocoder))
    t1.start()
    return api_output(request_id, status)
  if 'request' in flask.request.args:
    request_id = flask.request.args['request']
    try:
      db_entry = ttsdb.check_request(request_id)
      return api_output(db_entry[1], RequestStatus(db_entry[3]))
    except:
      return api_output(request_id, RequestStatus.FAILED)
  else:
    return "Error."

@app.route('/api/v1/models', methods=['GET'])
@cross_origin()
def api_models():
  resp = {
    'timestamp': datetime.datetime.now(),
    'model_names': list(generators.keys())
  }
  return flask.jsonify(resp)

if __name__ == '__main__':
  generators = create_generators(config)
  app.run(host=config['host'], port=int(config['port']), debug=False)
