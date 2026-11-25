.PHONY: install run app test
install:
	pip install -r requirements.txt
run:            ## train models, simulate campaigns, build results (~10 s)
	python -m churnlab.pipeline
app:            ## dashboard on http://localhost:8000
	uvicorn churnlab.api:app --reload --port 8000
test:
	pytest -q
