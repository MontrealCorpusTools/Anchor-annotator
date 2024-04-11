

.. _known_issues:

************
Known issues
************


.. important::

   As Anchor is in alpha, it is also possible to get into unrecoverable states due to database corruption and not all edge cases are handled by Anchor yet.  I recommend installing `pgAdmin <https://www.pgadmin.org/>`_ so that you delete/drop databases as necessary for corpora.  Once a corpus database is dropped, then restarting Anchor will trigger loading it from scratch (if the "Autoload last used corpus" option is enabled in :ref:`general_options`)

Launching Anchor
================

.. error::

   :code:`This application failed to start because no Qt platform plugin could be initialized. Reinstalling the application may fix this problem.`

.. tip::

   Set the environment variable :code:`QT_PLUGIN_PATH=C:\Users\michael\miniconda3\envs\anchor\Library\lib\qt6\plugins`.

   * `Bash <https://www.howtogeek.com/668503/how-to-set-environment-variables-in-bash-on-linux/>`_
   * `Mac OSX <https://support.apple.com/guide/terminal/use-environment-variables-apd382cc5fa-4f58-4449-b20a-41c53c006f8f/mac>`_
   * `Windows command line <https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/set_1>`_

.. error::

   On MacOSX:

   .. code-block::

      Failed to initialize QAudioOutput "Could not find the autoaudiosink GStreamer element"
      zsh: segmentation fault  mfa anchor

.. tip::

   Run :code:`export QT_MEDIA_BACKEND=darwin`.
