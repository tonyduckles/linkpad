from setuptools import setup

setup(
    name='linkpad',
    version='0.1',
    py_modules=['linkpad'],
    install_requires=[
        'click',
        'pyyaml',
        'sh',
    ],
    entry_points='''
        [console_scripts]
        linkpad=linkpad:cli
    ''',
)
