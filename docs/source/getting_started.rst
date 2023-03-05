
***************
Getting started
***************


Installation
------------

.. grid:: 2

    .. grid-item-card:: Installing with conda
       :text-align: center
       :columns: 12


       .. code-block:: bash

          conda config --add channels conda-forge
          conda install montreal-forced-aligner
          pip install anchor

       +++

       .. button-link:: https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html
          :color: primary
          :expand:

          Install Conda


    .. grid-item-card:: Running anchor
       :text-align: center

       .. code-block:: bash

          mfa anchor


    .. grid-item-card:: First steps
       :text-align: center

       First time using Anchor? Want a walk-through of a specific use case?

       +++

       .. button-ref:: first_steps
          :expand:
          :color: primary

          First steps


.. toctree::
   :maxdepth: 1
   :hidden:

   installation
   first_steps/index
