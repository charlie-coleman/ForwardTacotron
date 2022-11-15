#!/bin/bash

tensorboard --logdir $PWD/checkpoints/ --samples_per_plugin=images=100 --port 8111 --bind_all &> $PWD/logs/tensorboard.log
