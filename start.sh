#!/bin/bash
gunicorn servidor_enjoy:app --bind 0.0.0.0:$PORT