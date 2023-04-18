# Changes to ARGDIT

This fork's sole pourpose was to add the functionality of speciying a config files for the pocesses that need it. This is just so the I can pass a config file through my workflow without needing to make my container writeable to fill in the config each time.

The changes were made to convert_id_uniprot_to_ncbi.py, merge_arg_db.py, and check_arg_db.py as these are the only ones that need access to the config.

Usage:

convert_id_uniprot_to_ncbi.py [optional argument] seq_db_path output_seq_db_path -con config.ini

merge_arg_db.py [optional arguments] -o OUTPUT_SEQ_DB_PATH seq_db_paths -con config.ini

check_arg_db.py [optional arguments] seq_db_path -con config.ini

Visit https://github.com/phglab/ARGDIT for documentation
