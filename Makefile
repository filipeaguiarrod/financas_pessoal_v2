PYTHON = .venv/Scripts/python
UV = uv run

install:
	$(PYTHON) -m pip install -r requirements.txt

run_local:
	$(UV) streamlit run app.py

compose_up:
	docker compose down --remove-orphans
	docker compose up --build -d

test_parcelas:
	$(UV) pytest tests/test_parcelas.py -v -s

clean:
	@echo "Limpando arquivos temporarios..."
	-del /s /q *.pyc
	-rmdir /s /q __pycache__ src\__pycache__
