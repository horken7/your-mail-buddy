from setuptools import setup, find_packages


def parse_requirements(filename):
    """Parse a requirements file into a list of strings."""
    with open(filename, 'r') as file:
        return [line.strip() for line in file if line.strip() and not line.startswith("#")]


# Read requirements
install_requires = parse_requirements('requirements.txt')
extra_requirements = {
    'dev': parse_requirements('requirements-dev.txt'),
}

setup(
    name="your-mail-buddy",
    version="0.1",
    packages=find_packages(where='src'),
    package_dir={"": "src"},
    install_requires=install_requires,
    extras_require=extra_requirements,
)
