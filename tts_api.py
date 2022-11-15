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

parser = argparse.ArgumentParser()
parser.add_argument('-t', '--tts_path', type=str, default="./ttsmodels/forward.pt", help="path to the TTS model checkpoint.")
parser.add_argument('-v', '--voc_path', type=str, default="./ttsmodels/wave.pt", help="path to the vocoder model checkpoint.")
parser.add_argument('-w', '--wav_path', type=str, default="./model_outputs/", help="path to which save wavs.")
parser.add_argument('-d', '--database_path', type=str, default="./api/api_db.db", help="path to the tts db")

args = parser.parse_args()

app = flask.Flask(__name__)
cors = CORS(app)
app.config["CORS_HEADERS"] = 'Content-Type'

wavegen = ForwardGenerator(args.tts_path, "wavernn", args.voc_path)
griffgen = ForwardGenerator(args.tts_path, "griffinlim")
ttsdb = API_DB(args.database_path)

def api_output(request_id, status):
  location = "" if status != RequestStatus.COMPLETED else f"https://media.luscious.dev/storage/{request_id}.wav"
  resp = {
    'id': request_id,
    'timestamp': datetime.datetime.now(),
    'status': status.value,
    'path': location
  }
  return flask.jsonify(resp)

def output_wav_path(request_id):
  return Path(args.wav_path) / f'{request_id}.wav'

def generate_wavernn_tts(request_id, text):
  try:
    wav_path = output_wav_path(request_id)
    wavegen.generate(text, str(wav_path))
    ttsdb.update_request_status(request_id, RequestStatus.COMPLETED)
  except:
    print("Failed to generate TTS output.")
    ttsdb.update_request_status(request_id, RequestStatus.FAILED)

def generate_grifflim_tts(request_id, text):
  try:
    wav_path = output_wav_path(request_id)
    griffgen.generate(text, str(wav_path))
    ttsdb.update_request_status(request_id, RequestStatus.COMPLETED)
  except:
    print("Failed to generate TTS output.")
    ttsdb.update_request_status(request_id, RequestStatus.FAILED)

@app.route('/', methods=['GET'])
@cross_origin()
def home():
  return """<h1>LusciousLollipop's TTS API.</h1>
            <p>Try <a href="https://tts.luscious.dev/api/v1/tts?text=Test%201%2C%202%2C%203%2C%204.">this</a></p>"""

@app.route('/api/v1/tts', methods=['GET'])
@cross_origin()
def api_tts():
  if 'text' in flask.request.args:
    text = flask.request.args['text']
    (request_id, status) = ttsdb.add_request(text)
    t1 = threading.Thread(target=generate_grifflim_tts, args=(request_id, text))
    t1.start()
    return api_output(request_id, status)
  if 'wavernn' in flask.request.args:
    text = flask.request.args['wavernn']
    (request_id, status) = ttsdb.add_request(text)
    t1 = threading.Thread(target=generate_wavernn_tts, args=(request_id, text))
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

if __name__ == '__main__':
  app.run(host="0.0.0.0", port=8073, debug=False)
