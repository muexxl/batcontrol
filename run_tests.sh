#!/bin/bash

# Activate virtual environment if it exists (if running outside of container)
if [ -f "bin/activate" ]; then
    source bin/activate
fi

# Install pytest dependencies if not already installed
pip install pytest pytest-cov

# Run tests with coverage
python -m pytest tests/ --cov=src/batcontrol

# Exit with the same status as pytest
exit $?
