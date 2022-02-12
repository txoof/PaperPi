# TO DO

## Installer
* [x] checks for required deb packages (some may be missing for pygal)
* [x] copies repo contents to an install location
* [x] builds pipenv with all requirements for all installed modules
* [x] creates launcher script that can be used to create pipenv venv and `pipenv run python3 paperpi.py` from outside of pipenv path
    - this is proving to be challenging see: this [solution](https://titanwolf.org/Network/Articles/Article?AID=41470348-ec29-40b8-9068-e19d4656137a) -- it partially works, but needs some heavy modification (remove spaces)
* [ ] creates systemd unit files and installs them properly
* [ ] creates /etc/ config files
* [ ] process for adding new modules and installing dependencies
* [ ] homebrew style installer that pulls files from github and installs directly `curl https://github.com/foo/install.sh | bash`
* [ ]

## Devel Environment
see the utilities dir

* [x] builds development environment from Pipfile
* [x] creates documentation on demand 
* [x] find imports from all plugins and create `requirements-plguinname.txt` for each
    - this will be a new requirement for all plugins so
* [ ] 

## MISC
* [ ] Sample .ini file is not being rebuilt with documentation -- this should happen with the `create_docs.py` script
* [ ] document how the creation of docs, paperpi.ini file get created

    