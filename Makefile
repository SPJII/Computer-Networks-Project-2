# Makefile for convenience running server and client

.PHONY: run-server run-client clean

run-server:
	python3 server.py

run-client:
	python3 client.py

clean:
	find . -name "__pycache__" -type d -exec rm -r {} +