#! /bin/bash

python ./tts_api.py -t ./ttsmodels/itswill_forward_step300k.pt -v ./ttsmodels/ljspeech_wave_step575k.pt -w /var/www/media.luscious.dev/storage &> ./logs/ttsapi.log
