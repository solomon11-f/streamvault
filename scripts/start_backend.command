#!/bin/bash
cd "$(dirname "$0")/../backend" || exit 1
npm install
node server.js
