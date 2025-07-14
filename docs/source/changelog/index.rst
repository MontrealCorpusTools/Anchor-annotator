
Changelog
=========

.. warning::

   Alpha releases

0.9.3
-----

- Fix issue in transcription fields not showing up
- Fix issue in transcription errors not highlighting correctly

0.9.0
-----

- Fixed issues when running Anchor on MacOSX

0.8.1
-----

- Fixed keyboard interaction on table views

0.8.0
-----

- Added support for whisper and speechbrain for transcribing utterances
- Added support for trimming utterance silence based on VAD
- Added VAD model selection to Model menu
- Added Language menu for use in whisper transcription
- Fixed a bug where alignment metrics were not being computed
- Improved search to better handle cases where diacritics were being treated as non-word symbols
- Improved transcription window functionality
- Compatibility with MFA 3.2.0

0.7.1
-----

- Fixed bug when editing text
- Disabled scrolling to the top when editing pronunciations

0.7.0
-----

- Refactored thread workers
- Optimized word and phone interval drawing
- Added transcript verification button to alignment window

0.5.0
-----

- Further optimize rendering of intervals for long files
- Added ability to use native OS theme instead of MFA theme
- Refactored icons and resources to optimize space

0.4.0
-----

- Fixed an issue when adding pronunciation for OOV item from normalized text window
- Fixed an issue where volume bar would not save volume properly
- Fixed an issue where punctuation would incorrectly label items as OOVs
- Fixed a display issue on tables in Windows
- Updated diarization code to be compatible with file optimizations in 0.2.0
- Improved regex search to not rely as much on postgres character classes (which are not unicode aware)

0.3.3
-----

- Fixed a bug in loading saved dictionaries and models

0.3.2
-----

- Fixed compatibility with Qt 6.7

0.3.1
-----

- Fixed a crash on launch

0.3.0
-----

- Added a corpus manager dialog to allow for cleaning up previously loaded corpora and more efficient loading with dictionaries and models
- Enabled volume slider control and mute
- Removed sync and reset actions on toolbar in favor of export files
- Fixed a visual bug in size of text grid area
- Added customizable settings for the maximum duration that pitch tracks and spectrograms will be show (by default 10 seconds is maximum for pitch and 30 seconds for spectrogram)
- Added setting for disabling audio fade in on playing

0.2.1
-----

- Fixed bug with calculated columns when merging/splitting and then changing time boundaries
- Fixed bug when double clicking on an utterance to focus it

0.2.0
-----

- Revamped and optimized utterance loading to improve performance for long sound files with many utterances
- Added ability to click on word intervals to highlight those words in transcripts

0.1.0
-----

- Added ability to swap time axis for right-to-left languages to preferences

0.0.11
------

- Updated documentation and examples for latest version
- Polished some UI elements with style sheets

0.0.10
------

- Updated compatibility with `MFA 3.0 <https://montreal-forced-aligner.readthedocs.io/en/latest/changelog/news_3.0.html>`_
