
.. _installation:

************
Installation
************


All platforms
=============

1. Install `Miniconda <https://docs.conda.io/en/latest/miniconda.html>`_/`Conda installation <https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html>`_
2. Create new environment and install MFA: :code:`conda create -n anchor -c conda-forge anchor-annotator`

   a.  You can enable the :code:`conda-forge` channel by default by running :code:`conda config --add channels conda-forge` in order to omit the :code:`-c conda-forge` from these commands

3. Ensure you're in the new environment created (:code:`conda activate anchor`)
4. Verify Anchor launches via :code:`mfa anchor`

.. warning::

   See :ref:`known_issues` if you encounter any errors.
