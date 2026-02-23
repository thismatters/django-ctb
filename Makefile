TEST_PATH = ""

migrations:
	cd test_project && uv run manage.py makemigrations
init:
	cd test_project && uv run manage.py migrate # && uv run manage.py loaddata fixtures/test_data.json
shell:
	cd test_project && uv run manage.py shell
run:
	cd test_project && uv run manage.py runserver 0.0.0.0:8000
run-worker:
	cd test_project && uv run manage.py rundramatiq --reload
lint:
	black django_ctb
	isort django_ctb
	cd django_ctb && pflake8
test:
	DJANGO_SETTINGS_MODULE=test_project.settings.test uv run pytest --cov=django_ctb --cov-report term-missing tests/$(TEST_PATH)
uml-diagram:
	cd test_project && uv run manage.py graph_models --pygraphviz -o models.png django_ctb
	mv test_project/models.png docs/source/_images/models.png
