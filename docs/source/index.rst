=====================================
Thenewboston blockchain documentation
=====================================

`1. File system storage`_

`1.1. Blockchain file structure`_

`1.2. File path optimization`_


1. File system storage
======================

Blockchain and root account files are stored on the filesystem
in two separate subdirectories named *"{{ file_blockchain.blocks_subdir }}"*
and *"{{ file_blockchain.account_root_file_subdir }}"* respectively.


1.1. Blockchain file structure
------------------------------

Validated blocks are stored in chunks of *{{ file_blockchain.block_chunk_size }}*
blocks. Block numeration starts with *0* and each subsequent block number is
incremented by *1*. Every block chunk is stored in a file named according to
the first block and the last block. In order to get a valid block chunk file
name:

#. First and last block numbers are converted to string and filled with leading
   zeros to get a string *{{ file_blockchain.order_of_block }}* characters long.
#. The results are used to format the template
   *"{{ file_blockchain.block_chunk_template }}"*


Example:
    Blocks since *100* till *199* will be saved to
    *{{ file_blockchain.get_block_chunk_filename(100, 199) }}*


1.2. File path optimization
---------------------------
