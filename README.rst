assisi-python
=============

.. image:: https://badge.fury.io/py/assisipy.svg
    :target: https://badge.fury.io/py/assisipy

.. image:: https://zenodo.org/badge/DOI/10.5281/zenodo.1320079.svg
   :target: https://dx.doi.org/10.5281/zenodo.1320079

Python API for the `ASSISI|bf <http://assisi-project.eu/>`__ project.

The API can be used to interact with CASUs and other system components, whether
in physical hardware or simulated in the `assisi-playground
<https://github.com/larics/assisi-playground>`__.

For a quick installation, use ``sudo pip install assisipy``.  
To find more information regarding installation, usage, and examples, consult
the `readthedocs instructions
<http://assisipy.readthedocs.io/en/latest/install.html>`__. 



Building the Python package and uploading it to PyPy
----------------------------------------------------

Assuming you have `~/.pypirc` already set up:

::

   python setup.py sdist
   twine upload dist/assisipy-x.y.z.tar.gz -p password


Installing the development version
----------------------------------

Local changes to the repo will be immediatelly visible in the
installed package (need to check this).

::

   sudo pip install -e .


To uninstall the development version:

::

   sudo python setup.py develop --uninstall


For more info see
http://python-packaging-user-guide.readthedocs.org/en/latest/distributing

