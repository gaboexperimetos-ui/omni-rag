PYTHON ?= python3

.PHONY: help test compile demo index install clean

help:
	@echo "make test     pruebas (unittest)"
	@echo "make compile  comprobación de sintaxis"
	@echo "make demo     indexa examples/vault-demo en .demo/config.json"
	@echo "make index    reindexa la biblioteca real"
	@echo "make install  instala el comando omni-rag (pip --user -e .)"
	@echo "make clean    borra __pycache__ y .demo"

test:
	$(PYTHON) -m unittest discover -s tests -v

compile:
	$(PYTHON) -m compileall -q omni_rag

demo:
	$(PYTHON) -m omni_rag --config .demo/config.json init --vault examples/vault-demo --name demo
	$(PYTHON) -m omni_rag --config .demo/config.json index
	$(PYTHON) -m omni_rag --config .demo/config.json overview

index:
	$(PYTHON) -m omni_rag index

install:
	$(PYTHON) -m pip install --user -e .

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .demo
