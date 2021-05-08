import logging
import os.path
import re
from typing import Generator, Optional

import msgpack
from cachetools import LRUCache
from more_itertools import always_reversible, ilen

from thenewboston_node.business_logic.models.account_root_file import AccountRootFile
from thenewboston_node.business_logic.models.block import Block
from thenewboston_node.business_logic.storages.path_optimized_file_system import PathOptimizedFileSystemStorage
from thenewboston_node.core.logging import timeit

from .base import BlockchainBase

logger = logging.getLogger(__name__)

# TODO(dmu) LOW: Move these constants to configuration files
ORDER_OF_ACCOUNT_ROOT_FILE = 10
ORDER_OF_BLOCK = 20

ACCOUNT_ROOT_FILE_FILENAME_TEMPLATE = '{last_block_number}-arf.msgpack'
BLOCK_CHUNK_FILENAME_TEMPLATE = '{start}-{end}-block-chunk.msgpack'
BLOCK_CHUNK_FILENAME_RE = re.compile(
    BLOCK_CHUNK_FILENAME_TEMPLATE.format(start=r'(?P<start>\d+)', end=r'(?P<end>\d+)')
)

DEFAULT_ACCOUNT_ROOT_FILE_SUBDIR = 'account-root-files'
DEFAULT_BLOCKS_SUBDIR = 'blocks'

DEFAULT_BLOCK_CHUNK_SIZE = 100


def get_start_end(file_path):
    filename = os.path.basename(file_path)
    match = BLOCK_CHUNK_FILENAME_RE.match(filename)
    if match:
        start = int(match.group('start'))
        end = int(match.group('end'))
        assert start <= end
        return start, end

    return None, None


def get_block_chunk_filename(start: int, end: int):
    start_block_str = str(start).zfill(ORDER_OF_BLOCK)
    end_block_str = str(end).zfill(ORDER_OF_BLOCK)

    block_chunk_filename = BLOCK_CHUNK_FILENAME_TEMPLATE.format(start=start_block_str, end=end_block_str)
    return block_chunk_filename


class FileBlockchain(BlockchainBase):

    def __init__(
        self,
        *,
        base_directory,

        # Account root files
        account_root_files_subdir=DEFAULT_ACCOUNT_ROOT_FILE_SUBDIR,
        account_root_files_cache_size=128,
        account_root_files_storage_kwargs=None,

        # Blocks
        blocks_subdir=DEFAULT_BLOCKS_SUBDIR,
        block_chunk_size=DEFAULT_BLOCK_CHUNK_SIZE,
        blocks_cache_size=None,
        blocks_storage_kwargs=None,
        **kwargs
    ):
        if not os.path.isabs(base_directory):
            raise ValueError('base_directory must be an absolute path')

        arf_creation_period_in_blocks = kwargs.setdefault('arf_creation_period_in_blocks', block_chunk_size)
        super().__init__(**kwargs)

        self.block_chunk_size = block_chunk_size

        account_root_files_directory = os.path.join(base_directory, account_root_files_subdir)
        block_directory = os.path.join(base_directory, blocks_subdir)

        self.block_storage = PathOptimizedFileSystemStorage(base_path=block_directory, **(blocks_storage_kwargs or {}))
        self.account_root_files_storage = PathOptimizedFileSystemStorage(
            base_path=account_root_files_directory, **(account_root_files_storage_kwargs or {})
        )

        self.account_root_files_cache = LRUCache(account_root_files_cache_size)
        self.blocks_cache = LRUCache(
            # We do not really need to cache more than `arf_creation_period_in_blocks` blocks since
            # we use use account root file as a base
            arf_creation_period_in_blocks * 2 if blocks_cache_size is None else blocks_cache_size
        )

    # Account root files methods
    def persist_account_root_file(self, account_root_file: AccountRootFile):
        storage = self.account_root_files_storage
        last_block_number = account_root_file.last_block_number

        prefix = ('.' if last_block_number is None else str(last_block_number)).zfill(ORDER_OF_ACCOUNT_ROOT_FILE)
        file_path = ACCOUNT_ROOT_FILE_FILENAME_TEMPLATE.format(last_block_number=prefix)
        storage.save(file_path, account_root_file.to_messagepack(), is_final=True)

    def _load_account_root_file(self, file_path):
        cache = self.account_root_files_cache
        account_root_file = cache.get(file_path)
        if account_root_file is None:
            storage = self.account_root_files_storage
            assert storage.is_finalized(file_path)
            account_root_file = AccountRootFile.from_messagepack(storage.load(file_path))
            cache[file_path] = account_root_file

        return account_root_file

    def _iter_account_root_files(self, direction) -> Generator[AccountRootFile, None, None]:
        assert direction in (1, -1)

        storage = self.account_root_files_storage
        for file_path in storage.list_directory(sort_direction=direction):
            yield self._load_account_root_file(file_path)

    def iter_account_root_files(self) -> Generator[AccountRootFile, None, None]:
        yield from self._iter_account_root_files(1)

    def iter_account_root_files_reversed(self) -> Generator[AccountRootFile, None, None]:
        yield from self._iter_account_root_files(-1)

    def get_account_root_file_count(self) -> int:
        storage = self.account_root_files_storage
        return ilen(storage.list_directory())

    # Blocks methods
    def persist_block(self, block: Block):
        storage = self.block_storage
        block_chunk_size = self.block_chunk_size

        block_number = block.message.block_number
        chunk_number, offset = divmod(block_number, block_chunk_size)

        chunk_block_number_start = chunk_number * block_chunk_size

        if chunk_block_number_start == block_number:
            append_end = block_number
        else:
            assert chunk_block_number_start < block_number
            append_end = block_number - 1

        append_filename = get_block_chunk_filename(start=chunk_block_number_start, end=append_end)
        filename = get_block_chunk_filename(start=chunk_block_number_start, end=block_number)

        storage.append(append_filename, block.to_messagepack())

        if append_filename != filename:
            storage.move(append_filename, filename)

        if offset == block_chunk_size - 1:
            storage.finalize(filename)

    def iter_blocks(self) -> Generator[Block, None, None]:
        yield from self._iter_blocks(1)

    @timeit(verbose_args=True, is_method=True)
    def iter_blocks_reversed(self) -> Generator[Block, None, None]:
        yield from self._iter_blocks(-1)

    def iter_blocks_from(self, block_number: int) -> Generator[Block, None, None]:
        for file_path in self._list_block_directory():
            start, end = get_start_end(file_path)
            if end < block_number:
                continue

            yield from self._iter_blocks_from_file_cached(file_path, direction=1, start=max(start, block_number))

    def get_block_by_number(self, block_number: int) -> Optional[Block]:
        block = self.blocks_cache.get(block_number)
        if block is not None:
            return block

        try:
            return next(self.iter_blocks_from(block_number))
        except StopIteration:
            return None

    def get_block_count(self) -> int:
        count = 0
        for file_path in self._list_block_directory():
            start, end = get_start_end(file_path)
            assert start is not None
            assert end is not None

            count += end - start + 1

        return count

    @timeit(verbose_args=True, is_method=True)
    def _iter_blocks(self, direction) -> Generator[Block, None, None]:
        assert direction in (1, -1)

        for file_path in self._list_block_directory(direction):
            yield from self._iter_blocks_from_file_cached(file_path, direction)

    def _iter_blocks_from_file_cached(self, file_path, direction, start=None):
        assert direction in (1, -1)

        file_start, file_end = get_start_end(file_path)
        if direction == 1:
            next_block_number = cache_start = file_start if start is None else start
            cache_end = file_end
        else:
            cache_start = file_start
            next_block_number = cache_end = file_end if start is None else start

        for block in self._iter_blocks_from_cache(cache_start, cache_end, direction):
            next_block_number = block.message.block_number + (1 if direction == 1 else -1)
            yield block

        if file_start <= next_block_number <= file_end:
            yield from self._iter_blocks_from_file(file_path, direction, start=next_block_number)

    def _iter_blocks_from_file(self, file_path, direction, start=None):
        assert direction in (1, -1)
        storage = self.block_storage

        unpacker = msgpack.Unpacker()
        unpacker.feed(storage.load(file_path))
        if direction == -1:
            unpacker = always_reversible(unpacker)

        for block_compact_dict in unpacker:
            block = Block.from_compact_dict(block_compact_dict)
            block_number = block.message.block_number
            # TODO(dmu) HIGH: Implement a better skip
            if start is not None:
                if direction == 1 and block_number < start:
                    continue
                elif direction == -1 and block_number > start:
                    continue

            self.blocks_cache[block_number] = block
            yield block

    def _iter_blocks_from_cache(self, start_block_number, end_block_number, direction):
        assert direction in (1, -1)

        iter_ = range(start_block_number, end_block_number + 1)
        if direction == -1:
            iter_ = always_reversible(iter_)

        for block_number in iter_:
            block = self.blocks_cache.get(block_number)
            if block is None:
                break

            yield block

    def _list_block_directory(self, direction=1):
        storage = self.block_storage
        yield from storage.list_directory(sort_direction=direction)
