=================
Python AMI Client
=================

.. image:: https://travis-ci.org/ettoreleandrotognoli/python-ami.svg?branch=master
    :target: https://travis-ci.org/ettoreleandrotognoli/python-ami

.. image:: https://codecov.io/gh/ettoreleandrotognoli/python-ami/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/ettoreleandrotognoli/python-ami

.. image:: https://badge.fury.io/py/asterisk-ami.svg
    :target: https://badge.fury.io/py/asterisk-ami

.. image:: https://img.shields.io/pypi/dm/asterisk-ami.svg
    :target: https://pypi.python.org/pypi/asterisk-ami#downloads

A simple Python AMI client
http://programandonoaquario.blogspot.com.br

See the `code of conduct <CODE_OF_CONDUCT.md>`_.

Install
-------

Install asyncami

.. code-block:: shell

    pip install asyncami

Install latest asyncami

.. code-block:: shell

    pip install git+https://github.com/smurfix/asyncami

Usage
-----

Connect
~~~~~~~

.. code-block:: python

    from asyncami import AMIClient
    
    async with AMIClient(address='127.0.0.1',port=5038) as client:
        await client.login(username='username',secret='password')
    
Disconnect
~~~~~~~~~~

.. code-block:: python

    await client.logoff()


Send an action
~~~~~~~~~~~~~~

.. code-block:: python

    from asyncami import SimpleAction
    
    action = SimpleAction(
        'Originate',
        Channel='SIP/2010',
        Exten='2010',
        Priority=1,
        Context='default',
        CallerID='python',
    )
    await client.send_action(action)


Send an action with adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from asterisk.ami import AMIClientAdapter
    
    adapter = AMIClientAdapter(client)
    adapter.Originate(
        Channel='SIP/2010',
        Exten='2010',
        Priority=1,
        Context='default',
        CallerID='python',
    )
    
Read a Response
~~~~~~~~~~~~~~~

.. code-block:: python

    # without adapter
    response = await client.send_action(action)
    
    #with adapter
    response = await adapter.Originate(...)
    

Listen for Events
~~~~~~~~~~~~~~~~~

.. code-block:: python

    async with client.event_listener(**kwargs) as listener:
        async for event in listener:
            print(event)
    

