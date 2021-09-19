from setuptools import setup
import codecs
import os.path


def readme():
    with open('README.md') as f:
        return f.read()


def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()


def get_version(rel_path):
    delim = ' = '
    for line in read(rel_path).splitlines():
        if line.startswith('__ver_major__'):
            major_version = line.split(delim)[1]
        elif line.startswith('__ver_minor__'):
            minor_version = line.split(delim)[1]
        elif line.startswith('__ver_patch__'):
            patch_version = line.split(delim)[1].replace("'", '')
            break
    else:
        raise RuntimeError("Unable to find version string.")
    return "{}.{}.{}".format(major_version, minor_version, patch_version)


if __name__ == '__main__':
    setup(name='Anchor annotator',
          description='Anchor annotator is a program for inspecting corpora for the Montreal Forced Aligner and '
                      'correcting transcriptions and pronunciations.',
          long_description=readme(),
          version=get_version("anchor/__init__.py"),
          long_description_content_type='text/markdown',
          classifiers=[
              'Development Status :: 3 - Alpha',
              'Programming Language :: Python',
              'Programming Language :: Python :: 3',
              'Operating System :: OS Independent',
              'Topic :: Scientific/Engineering',
              'Topic :: Text Processing :: Linguistic',
          ],
          keywords='speech corpus annotation transcription',
          url='https://github.com/MontrealCorpusTools/Anchor-annotator',
          author='Montreal Corpus Tools',
          author_email='michael.e.mcauliffe@gmail.com',
          packages=['anchor'],
          install_requires=[
              'praatio ~= 4.1',
              'numpy',
              'tqdm',
              'pyyaml',
              'librosa',
              'requests',
              'sklearn',
              'joblib'
          ],
          python_requires='>=3.8',
          entry_points={
              'console_scripts': ['anchor=anchor.command_line:run_anchor']
          }
          )
