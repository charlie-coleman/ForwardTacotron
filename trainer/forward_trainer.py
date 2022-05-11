import time
from typing import Tuple, Dict, Any, Union

import torch
import torch.nn.functional as F
from torch.optim.optimizer import Optimizer
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

from models.fast_pitch import FastPitch
from models.forward_tacotron import ForwardTacotron
from trainer.common import Averager, TTSSession, MaskedL1, to_device, np_now
from utils.checkpoints import  save_checkpoint
from utils.dataset import get_tts_datasets
from utils.decorators import ignore_exception
from utils.display import stream, simple_table, plot_mel, plot_pitch
from utils.dsp import DSP
from utils.files import parse_schedule
from utils.paths import Paths


class ForwardTrainer:

    def __init__(self,
                 paths: Paths,
                 dsp: DSP,
                 config: Dict[str, Any]) -> None:
        self.paths = paths
        self.dsp = dsp
        self.config = config
        model_type = config.get('tts_model', 'forward_tacotron')
        self.train_cfg = config[model_type]['training']
        self.writer = SummaryWriter(log_dir=paths.forward_log, comment='v1')
        self.l1_loss = MaskedL1()
        self.ce_loss = torch.nn.CrossEntropyLoss(ignore_index=511)

    def train(self, model: Union[ForwardTacotron, FastPitch], optimizer: Optimizer) -> None:
        forward_schedule = self.train_cfg['schedule']
        forward_schedule = parse_schedule(forward_schedule)
        for i, session_params in enumerate(forward_schedule, 1):
            lr, max_step, bs = session_params
            if model.get_step() < max_step:
                train_set, val_set = get_tts_datasets(
                    path=self.paths.data, batch_size=bs, r=1, model_type='forward',
                    max_mel_len=self.train_cfg['max_mel_len'],
                    filter_attention=self.train_cfg['filter_attention'],
                    filter_min_alignment=self.train_cfg['min_attention_alignment'],
                    filter_min_sharpness=self.train_cfg['min_attention_sharpness'])
                session = TTSSession(
                    index=i, r=1, lr=lr, max_step=max_step,
                    bs=bs, train_set=train_set, val_set=val_set)
                self.train_session(model, optimizer, session)

    def train_session(self,  model: Union[ForwardTacotron, FastPitch],
                      optimizer: Optimizer, session: TTSSession) -> None:
        current_step = model.get_step()
        training_steps = session.max_step - current_step
        total_iters = len(session.train_set)
        epochs = training_steps // total_iters + 1
        simple_table([(f'Steps', str(training_steps // 1000) + 'k Steps'),
                      ('Batch Size', session.bs),
                      ('Learning Rate', session.lr)])

        for g in optimizer.param_groups:
            g['lr'] = session.lr

        m_loss_avg = Averager()
        dur_loss_avg = Averager()
        duration_avg = Averager()
        pitch_loss_avg = Averager()
        device = next(model.parameters()).device  # use same device as model parameters
        for e in range(1, epochs + 1):
            for i, batch in enumerate(session.train_set, 1):
                batch = to_device(batch, device=device)
                start = time.time()
                model.train()

                pitch_target = batch['pitch'].detach().clone().long()
                pitch_target = torch.clamp(pitch_target, min=0, max=511)
                pred = model(batch)
                pitch_loss = self.ce_loss(pred['pitch'], pitch_target)

                loss = pitch_loss

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(),
                                               self.train_cfg['clip_grad_norm'])
                optimizer.step()

                step = model.get_step()
                k = step // 1000

                duration_avg.add(time.time() - start)
                pitch_loss_avg.add(pitch_loss.item())

                speed = 1. / duration_avg.get()
                msg = f'| Epoch: {e}/{epochs} ({i}/{total_iters}) | Mel Loss: {m_loss_avg.get():#.4} ' \
                      f'| Dur Loss: {dur_loss_avg.get():#.4} | Pitch Loss: {pitch_loss_avg.get():#.4} ' \
                      f'| {speed:#.2} steps/s | Step: {k}k | '

                if step % self.train_cfg['checkpoint_every'] == 0:
                    save_checkpoint(model=model, optim=optimizer, config=self.config,
                                    path=self.paths.forward_checkpoints / f'forward_step{k}k.pt')

                if step % self.train_cfg['plot_every'] == 0:
                    self.generate_plots(model, session)

                self.writer.add_scalar('Pitch_Loss/train', pitch_loss, model.get_step())

                self.writer.add_scalar('Params/batch_size', session.bs, model.get_step())
                self.writer.add_scalar('Params/learning_rate', session.lr, model.get_step())

                stream(msg)

            val_out = self.evaluate(model, session.val_set)
            self.writer.add_scalar('Pitch_Loss/val', val_out['pitch_loss'], model.get_step())
            save_checkpoint(model=model, optim=optimizer, config=self.config,
                            path=self.paths.forward_checkpoints / 'latest_model.pt')

            m_loss_avg.reset()
            duration_avg.reset()
            pitch_loss_avg.reset()
            print(' ')

    def evaluate(self, model: Union[ForwardTacotron, FastPitch], val_set: DataLoader) -> Dict[str, float]:
        model.eval()
        pitch_val_loss = 0
        device = next(model.parameters()).device
        for i, batch in enumerate(val_set, 1):
            batch = to_device(batch, device=device)
            with torch.no_grad():
                pred = model(batch)
                pitch_target = batch['pitch'].detach().clone().long()
                pitch_target = torch.clamp(pitch_target, min=0, max=511)
                pitch_loss = self.ce_loss(pred['pitch'], pitch_target)
                pitch_val_loss += pitch_loss
        return {
            'pitch_loss': pitch_val_loss / len(val_set),
        }

    @ignore_exception
    def generate_plots(self, model: Union[ForwardTacotron, FastPitch], session: TTSSession) -> None:
        model.eval()
        device = next(model.parameters()).device
        batch = session.val_sample
        batch = to_device(batch, device=device)

        pred = model(batch)

        pitch_fig = plot_pitch(np_now(batch['pitch'][0]))

        pred_pitch = pred['pitch'].squeeze()[0]
        pred_inds = torch.argmax(pred_pitch, dim=0)
        pred_pitch_norm = pred_pitch.softmax(0)
        pred_probs = torch.zeros(len(pred_inds))
        for i in range(len(pred_inds)):
            pred_probs[i] = pred_pitch_norm[pred_inds[i], i]
        pred_inds = torch.clamp(pred_inds, min=0, max=400)
        pitch_gta_fig = plot_pitch(np_now(pred_inds))
        pitch_prob_fig = plot_pitch(np_now(pred_probs))

        self.writer.add_figure('Pitch/target', pitch_fig, model.step)
        self.writer.add_figure('Pitch/pred_pitch', pitch_gta_fig, model.step)
        self.writer.add_figure('Pitch/pred_probs', pitch_prob_fig, model.step)

        pred_inds_2 = torch.argmax(pred_pitch[1:, :], dim=0)
        pred_inds_2 = torch.clamp(pred_inds_2, min=0, max=400)
        pitch_inds_2_fig = plot_pitch(np_now(pred_inds_2))
        self.writer.add_figure('Pitch/pred_pitch_thres_0', pitch_inds_2_fig, model.step)

        pred_inds_3 = torch.argmax(pred_pitch[1:, :], dim=0)
        pred_probs = torch.zeros(len(pred_inds))
        for i in range(len(pred_inds_3)):
            pred_probs[i] = pred_pitch_norm[pred_inds_3[i], i]
            if pred_probs[i] < 0.01:
                pred_inds_3[i] = 0
        pred_inds_3 = torch.clamp(pred_inds_3, min=0, max=400)
        pitch_inds_3_fig = plot_pitch(np_now(pred_inds_3))
        self.writer.add_figure('Pitch/pred_pitch_thres_001', pitch_inds_3_fig, model.step)
