#!/bin/bash

gunicorn -c etc/gunicorn_config.py -w 1 -b 0.0.0.0:8082 app:app