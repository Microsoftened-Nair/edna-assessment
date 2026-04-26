from Bio import SeqIO
record = next(SeqIO.parse("/home/megh/edna/data/real_16s_labeled/trainset16_022016.pds/trainset16_022016.pds.fasta", "fasta"))
print(repr(record.id))
print(repr(record.description))
