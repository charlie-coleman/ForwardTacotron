import gen_forward as ttsgen
import flask
import uuid
from pathlib import Path
import os
import datetime
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--path', type=str, required=True, help="path to which save wavs.")

args = parser.parse_args()

app = flask.Flask(__name__)

def api_output(request_id, wav_location):
  resp = {
    'id': request_id,
    'timestamp': datetime.datetime.now(),
    'path': f"https://luscious.dev/tts/{request_id}.wav"
  }
  return flask.jsonify(resp)

@app.route('/', methods=['GET'])
def home():
  return "<h1>Testing this api.</h1>"

@app.route('/api/v1/tts', methods=['GET'])
def api_tts():
  if 'text' in flask.request.args:
    text = flask.request.args['text']
    request_id = str(uuid.uuid4())[:8]
    output_path = Path(args.path) / f'{request_id}.wav'
    ttsgen.generate('./ttsmodels/itswill_forward_step300k.pt', 'griffinlim', output_path=str(output_path), input_text=text)
    return api_output(request_id, output_path)
  else:
    return "Error."

if __name__ == '__main__':
  app.run(host="localhost", port=7373, debug=True)