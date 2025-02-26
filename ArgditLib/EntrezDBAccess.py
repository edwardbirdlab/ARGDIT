'''Module to perform NCBI database access via Entrez utilities'''

from Bio import Entrez
from Bio import SeqIO
from .EntrezRecordParser import *
from .ProcLog import ProcLog
from .Utils import split_wgs_acc_nums
from urllib.error import HTTPError, URLError
import re
import time

EPOST_FT_BATCH_SIZE = 100
EPOST_SEQ_BATCH_SIZE = 100
EFETCH_BATCH_SIZE = 100
MAX_ATTEMPT = 3

Entrez.tool = 'ARGDIT'

'''
Function name: set_entrez_email
Inputs       : Email address
Outputs      : Nil
Description  : Sets the user email address in Entrez before any database access
'''
def set_entrez_email(email):
    Entrez.email = email

'''
Function name: _split_acc_nums_into_batch
Inputs       : Query accession numbers for epost/efetch action, maximum accession number count in a
               batch
Outputs      : Batches of accession numbers
Description  : Splits the query accession numbers into disjoint accession number sets (batches), of
               which the maximum batch size is limited. This avoids too many accession numbers in a
               single Entrez epost/efetch query
'''
def _split_acc_nums_into_batch(acc_nums, batch_size = EFETCH_BATCH_SIZE):
    if type(acc_nums) is set:
        acc_num_set = acc_nums
    else:
        acc_num_set = set(acc_nums)

    acc_num_list = list(acc_num_set)
    acc_num_batches = list()
    acc_num_count = len(acc_num_list)
    extract_start = 0

    while extract_start < acc_num_count:
        extract_end = min((extract_start + batch_size), acc_num_count)
        acc_num_batches.append(acc_num_list[extract_start:extract_end])
        extract_start = extract_end

    return acc_num_batches

'''
Function name: _entrez_post
Inputs       : NCBI database name, query accession numbers
Outputs      : A 3-tuple containing query key, web environment, and errors occurred, or a 3-tuple of
               None
Description  : Performs the Entrez epost action and parses the returned handle to obtain the query
               key and web environment for the subsequent efetch action
'''
def _entrez_post(db_name, acc_nums):
    if Entrez.email is None:
        ProcLog.log_exec_error('Email address for Entrez is not set')
        return None, None, None

    attempt = 0
    while attempt < MAX_ATTEMPT:
        try:
            with Entrez.epost(db = db_name, id = ','.join(acc_nums)) as handle:
                efetch_query_key, web_env, errors = EPostParser.parse(handle)
                return efetch_query_key, web_env, errors
        except HTTPError as http_error:
            if 400 <= http_error.code <= 599:
                time.sleep(20)
                attempt += 1
                continue
            else:
                ProcLog.log_exec_error('epost(): {}'.format(http_error.reason))
                return None, None, None
        except URLError as url_error:
            ProcLog.log_exec_error('epost(): {}'.format(str(url_error.reason)))
            return None, None, None

    if attempt == MAX_ATTEMPT:
        ProcLog.log_exec_error('Attempted epost() 3 times and failed')
        return None, None, None

'''
Function name: _entrez_fetch_hist
Inputs       : NCBI database name, query key, web environment, record section to fetch, data type to
               fetch, record position to start fetching
Outputs      : Data handle or None
Description  : Performs the Entrez efetch action after epost and returns the data handle for subsequent
               parsing, or None if error occurs
'''
def _entrez_fetch_hist(db_name, efetch_query_key, web_env, return_section, return_type, fetch_start):
    attempt = 0
    while attempt < MAX_ATTEMPT:
        try:
            handle = Entrez.efetch(db = db_name, query_key = efetch_query_key, WebEnv = web_env,
                                   rettype = return_section, retmode = return_type, retmax = EFETCH_BATCH_SIZE,
                                   retstart = fetch_start)
            return handle
        except HTTPError as http_error:
            if 400 <= http_error.code <= 599:
                time.sleep(20)
                attempt += 1
                continue
            else:
                ProcLog.log_exec_error('efetch(): {}'.format(http_error.reason))
                return None
        except URLError as url_error:
            ProcLog.log_exec_error('efetch(): {}'.format(str(url_error.reason)))
            return None

    if attempt == MAX_ATTEMPT:
        ProcLog.log_exec_error('Attempted efetch() 3 times and failed')
        return None

'''
Function name: _entrez_fetch
Inputs       : NCBI database name, query accession numbers, record section to fetch, data type to
               fetch
Outputs      : Data handle or None
Description  : Performs the Entrez efetch action and returns the data handle for subsequent parsing, or
               None if error occurs
'''
def _entrez_fetch(db_name, acc_nums, return_section, return_type):
    if Entrez.email is None:
        ProcLog.log_exec_error('Email address for Entrez is not set')
        return None, None, None

    attempt = 0
    while attempt < MAX_ATTEMPT:
        try:
            handle = Entrez.efetch(db = db_name, id = ','.join(acc_nums), rettype = return_section,
                                   retmode = return_type)
            return handle
        except HTTPError as http_error:
            if 400 <= http_error.code <= 599:
                time.sleep(20)
                attempt += 1
                continue
            else:
                ProcLog.log_exec_error('efetch(): {}'.format(http_error.reason))
                return None
        except URLError as url_error:
            ProcLog.log_exec_error('efetch(): {}'.format(str(url_error.reason)))
            return None

    if attempt == MAX_ATTEMPT:
        ProcLog.log_exec_error('Attempted efetch() 3 times and failed')
        return None

'''
Function name: _search_entrez
Inputs       : Query accession numbers, data handle parser, NCBI database name, record section to
               fetch, data type to fetch, maximum accession number count for batch
Outputs      : Nil
Description  : Generic NCBI database searching function via Entrez utilities. It first splits the query
               accession numbers into WGS and non-WGS accession numbers. For each batch of query
               non-WGS accession numbers, it invokes entrez_post to obtain the query key and web
               environment, and then uses them to invoke entrez_fetch_hist to obtain the handle for the
               data returned. For WGS accession numbers, entrez_fetch is called to invoke Entrez efetch
               action directly to obtain the data handle. The parser specified in the input argument
               then parses the returned handle to extract the required data
'''
def _search_entrez(acc_nums, entrez_parser, db_name = 'nucleotide', return_section = 'ft', return_type = 'text',
                   epost_batch_size = EPOST_SEQ_BATCH_SIZE):
    wgs_acc_nums, non_wgs_acc_nums = split_wgs_acc_nums(acc_nums)

    for acc_num_epost_batch in _split_acc_nums_into_batch(non_wgs_acc_nums, epost_batch_size):
        '''print(len(acc_num_epost_batch))'''
        efetch_query_key, web_env, errors = _entrez_post(db_name, acc_num_epost_batch)
        if efetch_query_key is None:
            return

        '''print('{}, {}'.format(efetch_query_key, web_env))'''

        fetch_start = 0
        fetch_iter = (len(acc_num_epost_batch) + EFETCH_BATCH_SIZE - 1) // EFETCH_BATCH_SIZE
        i = 0

        while i < fetch_iter:
            handle = _entrez_fetch_hist(db_name, efetch_query_key, web_env, return_section, return_type, fetch_start)
            if handle is None:
                return

            entrez_parser.parse(handle)
            if hasattr(entrez_parser, 'is_parse_complete') and not entrez_parser.is_parse_complete:
                return

            fetch_start += EFETCH_BATCH_SIZE
            i += 1

        time.sleep(3)

    for acc_num_efetch_batch in _split_acc_nums_into_batch(wgs_acc_nums, EFETCH_BATCH_SIZE):
        handle = _entrez_fetch(db_name, acc_num_efetch_batch, return_section, return_type)
        if handle is None:
            return

        entrez_parser.parse(handle)
        if hasattr(entrez_parser, 'is_parse_complete') and not entrez_parser.is_parse_complete:
            return

        time.sleep(5)

'''
Function name: search_target_cds_by_nt_acc_num
Inputs       : Nucleotide accession numbers, CDS sequence length filters (optional)
Outputs      : Categorized CDS information, target protein accession numbers (IDs), and parse complete
               boolean
Description  : Searches the target CDS information according to the specified nucleotide accession
               numbers
'''
def search_target_cds_by_nt_acc_num(nt_acc_nums, cds_seq_len_filters = None):
    ft_cds_parser = FeatTblCDSParser(cds_seq_len_filters)
    _search_entrez(acc_nums = nt_acc_nums, entrez_parser = ft_cds_parser, epost_batch_size = EPOST_FT_BATCH_SIZE)

    return ft_cds_parser.get_target_cds_region_groups(), ft_cds_parser.get_target_protein_ids(), \
        ft_cds_parser.is_parse_complete

'''
Function name: search_protein_info
Inputs       : Protein accession numbers
Outputs      : Target protein information
Description  : Searches the target protein information according to the specified protein accession
               numbers
'''
def search_protein_info(protein_acc_nums):
    protein_xml_parser = ProteinXMLParser()
    _search_entrez(acc_nums = protein_acc_nums, entrez_parser = protein_xml_parser, db_name = 'protein',
                   return_section = 'gp', return_type = 'xml')

    return protein_xml_parser.get_protein_info_set()

'''
Function name: search_protein_seqs
Inputs       : Protein accession numbers
Outputs      : Target protein sequences
Description  : Searches the target protein sequences according to the specified protein accession
               numbers
'''
def search_protein_seqs(protein_acc_nums):
    protein_seq_parser = ProteinSeqParser()
    _search_entrez(acc_nums = protein_acc_nums, entrez_parser = protein_seq_parser, db_name = 'protein',
                   return_section = 'fasta', return_type = 'text')

    return protein_seq_parser.get_protein_seqs()

'''
Function name: _search_seq_status
Inputs       : Nucleotide/Protein accession numbers and the biological sequence (either nucleotide
               or protein) database to retrieve
Outputs      : Sequence accession numbers, sequence current status, and the accession numbers of
               the replacing sequences (if applicable)
Description  : Base function to retrieve the current status of the input accession numbers
'''
def _search_seq_status(acc_nums, db_name):
    doc_summary_parser = DocSummaryParser()
    _search_entrez(acc_nums = acc_nums, entrez_parser = doc_summary_parser, db_name = db_name,
                   return_section = 'docsum', return_type = 'xml')

    return doc_summary_parser.get_seq_status()

'''
Function name: search_nucleotide_seq_status
Inputs       : Nucleotide accession numbers
Outputs      : Sequence status, and the accession numbers of the replacing nucleotide sequences (if
               applicable)
Description  : Retrieve the current status of the input nucleotide accession numbers
'''
def search_nucleotide_seq_status(nt_acc_nums):
    return _search_seq_status(acc_nums = nt_acc_nums, db_name = 'nucleotide')

'''
Function name: search_protein_seq_status
Inputs       : Protein accession numbers
Outputs      : Sequence status, and the accession numbers of the replacing protein sequences (if
               applicable)
Description  : Retrieve the current status of the input protein accession numbers
'''
def search_protein_seq_status(protein_acc_nums):
    return _search_seq_status(acc_nums = protein_acc_nums, db_name = 'protein')

'''
def search_protein_info(protein_acc_nums):
    protein_seq_record_parser = ProteinSeqRecordParser()
    _search_entrez(acc_nums = protein_acc_nums, entrez_parser = protein_seq_record_parser, db_name = 'protein',
                   return_section = 'fasta', return_type = 'text')

    return protein_seq_record_parser.get_protein_info_set()
'''

'''For debug only'''
def _search_entrez_hist(efetch_query_key, web_env, query_item_count, entrez_parser, db_name = 'nucleotide',
                        return_section = 'ft', return_type = 'text'):
    fetch_start = 0
    fetch_iter = (query_item_count + EFETCH_BATCH_SIZE - 1) // EFETCH_BATCH_SIZE
    i = 0

    while i < fetch_iter:
        handle = _entrez_fetch_hist(db_name, efetch_query_key, web_env, return_section, return_type, fetch_start)
        if handle is None:
            return

        entrez_parser.parse(handle)
        if hasattr(entrez_parser, 'is_parse_complete') and not entrez_parser.is_parse_complete:
            return

        fetch_start += EFETCH_BATCH_SIZE
        i += 1

    time.sleep(3)

'''For debug only'''
def search_target_cds_by_nt_acc_num_hist(efetch_query_key, web_env, query_item_count, cds_seq_len_filters = None):
    ft_cds_parser = FeatTblCDSParser(cds_seq_len_filters)
    _search_entrez_hist(efetch_query_key, web_env, query_item_count, entrez_parser = ft_cds_parser)

    return ft_cds_parser.get_target_cds_region_groups(), ft_cds_parser.get_target_protein_ids(), \
        ft_cds_parser.is_parse_complete

'''For debug only'''
def search_protein_info_hist(efetch_query_key, web_env, query_item_count):
    protein_xml_parser = ProteinXMLParser()
    _search_entrez_hist(efetch_query_key, web_env, query_item_count, entrez_parser = protein_xml_parser,
                        db_name = 'protein', return_section = 'gp', return_type = 'xml')

    return protein_xml_parser.get_protein_info_set()

'''For debug only'''
def search_protein_seqs_hist(efetch_query_key, web_env, query_item_count):
    protein_seq_parser = ProteinSeqParser()
    _search_entrez_hist(efetch_query_key, web_env, query_item_count, entrez_parser = protein_seq_parser,
                        db_name = 'protein', return_section = 'fasta', return_type = 'text')

    return protein_seq_parser.get_protein_seqs()

'''
def search_protein_info_hist(efetch_query_key, web_env, query_item_count):
    protein_seq_record_parser = ProteinSeqRecordParser()
    _search_entrez_hist(efetch_query_key, web_env, query_item_count, entrez_parser = protein_seq_record_parser,
                        db_name = 'protein', return_section = 'fasta', return_type = 'text')

    return protein_seq_record_parser.get_protein_info_set()
'''
