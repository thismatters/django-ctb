TEST_PATH = ""

migrations:
	cd test_project && python manage.py makemigrations
init:
	cd test_project && python manage.py migrate # && python manage.py loaddata fixtures/test_data.json
run:
	cd test_project && python manage.py runserver 0.0.0.0:8000
run-worker:
	cd test_project && python manage.py rundramatiq --reload
lint:
	black django_ctb
	isort django_ctb
	cd django_ctb && pflake8
test:
	DJANGO_SETTINGS_MODULE=test_project.settings.test pytest --cov=django_ctb --cov-report term-missing tests/$(TEST_PATH)
uml-diagram:
	cd test_project && python manage.py graph_models --pygraphviz -o models.png
	mv test_project/models.png docs/source/_static/models.png