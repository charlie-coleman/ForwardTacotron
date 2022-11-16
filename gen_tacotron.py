import argparse
from pathlib import Path
import numpy as np
from typing import Tuple, Dict, Any

import torch

from models.fatchord_version import WaveRNN
from models.tacotron import Tacotron
from utils.display import simple_table
from utils.dsp import DSP
from utils.files import read_config
from utils.paths import Paths
from utils.text.cleaners import Cleaner
from utils.text.tokenizer import Tokenizer


def load_taco(checkpoint_path: str) -> Tuple[Tacotron, Dict[str, Any]]:
    print(f'Loading tts checkpoint {checkpoint_path}')
    checkpoint = torch.load(checkpoint_path, map_location=torch.device('cpu'))
    config = checkpoint['config']
    tts_model = Tacotron.from_config(config)
    tts_model.load_state_dict(checkpoint['model'])
    print(f'Loaded taco with step {tts_model.get_step()}')
    return tts_model, config


def load_wavernn(checkpoint_path: str) -> Tuple[WaveRNN, Dict[str, Any]]:
    print(f'Loading voc checkpoint {checkpoint_path}')
    checkpoint = torch.load(checkpoint_path, map_location=torch.device('cpu'))
    config = checkpoint['config']
    voc_model = WaveRNN.from_config(config)
    voc_model.load_state_dict(checkpoint['model'])
    print(f'Loaded wavernn with step {voc_model.get_step()}')
    return voc_model, config

class TacotronGenerator:
  tts_model = None
  voc_model = None
  tts_config = None
  voc_config = None
  tts_dsp = None
  voc_dsp = None

  cleaner = None
  tokenizer = None

  vocoder_type = ""
  device = None

  def __init__(self, checkpoint_path, vocoder_type, vocoder_checkpoint_path = ""):
    self.vocoder_type = vocoder_type
    self.tts_model, self.tts_config = load_taco(checkpoint_path)
    self.tts_dsp = DSP.from_config(self.tts_config)

    if self.vocoder_type == 'wavernn':
      self.voc_model, self.voc_config = load_wavernn(vocoder_checkpoint_path)
      self.voc_dsp = DSP.from_config(self.voc_config)

    self.device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
    self.tts_model.to(self.device)

    self.cleaner = Cleaner.from_config(self.tts_config)
    self.tokenizer = Tokenizer()

    tts_k = self.tts_model.get_step() // 1000
    self.tts_model.eval()

    simple_table([('Tacotron', str(tts_k) + 'k'), ('Vocoder Type', vocoder_type)])

  def generate(self, input_text, output_path, steps = 1000, overlap = 550, target = 11000):
    outpath = Path(output_path)
    outpath.parent.mkdir(parents=True, exist_ok=True)

    text = input_text
    text = self.cleaner(text)
    print("Cleaned text.")
    text = self.tokenizer(text)
    print("Tokenized text.")
    text = torch.as_tensor(text, dtype=torch.long, device=self.device).unsqueeze(0)

    print("Generating TTS input to vocoder.")
    _, m, _ = self.tts_model.generate(x=text, steps=steps)

    print("Vocoding...")
    if self.vocoder_type == 'melgan':
        m = torch.tensor(m).unsqueeze(0)
        torch.save(m, str(outpath))
    elif self.vocoder_type == 'hifigan':
        np.save(str(outpath), m.numpy(), allow_pickle=False)
    elif self.vocoder_type == 'wavernn':
        m = torch.tensor(m).unsqueeze(0)
        wav = self.voc_model.generate(mels=m,
                                      batched=True,
                                      target=target,
                                      overlap=overlap,
                                      mu_law=self.voc_dsp.mu_law)
        self.tts_dsp.save_wav(wav, str(outpath))
    elif self.vocoder_type == 'griffinlim':
        wav = self.tts_dsp.griffinlim(m)
        self.tts_dsp.save_wav(wav, str(outpath))

  def generate_grifflim(self, input_text, output_path, steps=1000, overlap = 550, target = 11000):
    outpath = Path(output_path)
    outpath.parent.mkdir(parents=True, exist_ok=True)

    text = input_text
    text = self.cleaner(text)
    print("Cleaned text.")
    text = self.tokenizer(text)
    print("Tokenized text.")
    text = torch.as_tensor(text, dtype=torch.long, device=self.device).unsqueeze(0)

    print("Generating TTS input to vocoder.")
    _, m, _ = self.tts_model.generate(x=text, steps=steps)

    print("Vocoding...")
    wav = self.tts_dsp.griffinlim(m)
    self.tts_dsp.save_wav(wav, str(outpath))

def generate(checkpoint_path, vocoder, voc_checkpoint_path = "", input_text = "", output_path = "", steps=1000, overlap = 550, target = 11000):
  tts_model, config = load_taco(checkpoint_path)
  dsp = DSP.from_config(config)

  voc_model, voc_dsp = None, None
  if vocoder == 'wavernn':
    voc_model, voc_config = load_wavernn(voc_checkpoint_path)
    voc_dsp = DSP.from_config(voc_config)

  out_path = Path('model_outputs/tacotron')
  out_path.mkdir(parents=True, exist_ok=True)
  device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
  tts_model.to(device)
  cleaner = Cleaner.from_config(config)
  tokenizer = Tokenizer()

  print(f'Using device: {device}\n')
  if input_text:
    texts = [input_text]
  else:
    with open('sentences.txt', 'r', encoding='utf-8') as f:
      texts = f.readlines()

  tts_k = tts_model.get_step() // 1000
  tts_model.eval()

  simple_table([('Tacotron', str(tts_k) + 'k'),
  ('Vocoder Type', vocoder)])

  for i, x in enumerate(texts, 1):
    print(f'\n| Generating {i}/{len(texts)}')
    x = cleaner(x)
    print("Cleaned text.")
    x = tokenizer(x)
    print("Tokenized text.")
    x = torch.as_tensor(x, dtype=torch.long, device=device).unsqueeze(0)

    wav_name = f'{i}_taco_{tts_k}k_{vocoder}'

    tts_name = config['tts_model_id']
    wav_name = f'{tts_name}_{tts_k}k_{i}'
    wavpath = None if output_path == None else output_path.format(i)
    if wavpath == None:
      wavpath = out_path / f'{wav_name}.wav'

    print("Generating TTS input to vocoder.")
    _, m, _ = tts_model.generate(x=x, steps=steps)

    print("Vocoding...")
    if vocoder == 'melgan':
      m = torch.tensor(m).unsqueeze(0)
      torch.save(m, out_path / f'{wav_name}.mel')
    if vocoder == 'hifigan':
      m = torch.tensor(m).unsqueeze(0)
      np.save(out_path / f'{wav_name}.npy', m.numpy(), allow_pickle=False)
    if vocoder == 'wavernn':
      m = torch.tensor(m).unsqueeze(0)
      wav = voc_model.generate(mels=m,
                               batched=True,
                               target=target,
                               overlap=overlap,
                               mu_law=voc_dsp.mu_law)
      dsp.save_wav(wav, wavpath)
    elif vocoder == 'griffinlim':
      wav = dsp.griffinlim(m)
      dsp.save_wav(wav, wavpath)

    print('\n\nDone.\n')

if __name__ == '__main__':
  # Parse Arguments
  parser = argparse.ArgumentParser(description='TTS Generator')
  parser.add_argument('--input_text', '-i', default=None, type=str, help='[string] Type in something here and TTS will generate it!')
  parser.add_argument('--checkpoint', '-c', type=str, default=None, help='[string/path] path to .pt model file.')
  parser.add_argument('--config', metavar='FILE', default='config.yaml', help='The config containing all hyperparams. Only'
                                                                              'used if no checkpoint is set.')
  parser.add_argument('--steps', type=int, default=1000, help='Max number of steps.')
  parser.add_argument('--output', type=str, default=None, help='[string/path]')

  # name of subcommand goes to args.vocoder
  subparsers = parser.add_subparsers(dest='vocoder')
  wr_parser = subparsers.add_parser('wavernn')
  wr_parser.add_argument('--overlap', '-o', default=550,  type=int, help='[int] number of crossover samples')
  wr_parser.add_argument('--target', '-t', default=11_000, type=int, help='[int] number of samples in each batch index')
  wr_parser.add_argument('--voc_checkpoint', '-v', type=str, help='[string/path] Load in different WaveRNN weights')

  gl_parser = subparsers.add_parser('griffinlim')
  mg_parser = subparsers.add_parser('melgan')

  args = parser.parse_args()

  assert args.vocoder in {'griffinlim', 'wavernn', 'melgan'}, \
      'Please provide a valid vocoder! Choices: [\'griffinlim\', \'wavernn\', \'melgan\']'

  if args.vocoder == "wavernn":
    generate(args.checkpoint, args.vocoder, args.voc_checkpoint, args.input_text, args.output, args.steps, args.overlap, args.target)
  else:
    generate(args.checkpoint, args.vocoder, input_text=args.input_text, output_path=args.output, steps=args.steps)
