PYTHON = .venv/Scripts/python

install:
	$(PYTHON) -m pip install -r requirements.txt

run_local:
	uv run streamlit run app.py

clean:
	@echo "Limpando arquivos temporarios..."
	-del /s /q *.pyc
	-rmdir /s /q __pycache__ src\__pycache__