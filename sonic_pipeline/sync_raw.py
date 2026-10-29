"""Legacy raw-first transfer is disabled by the user-authorized local workflow."""
def sync():
 raise ValueError('Raw sync retired: complete local review/conversion/cleaning/acceptance, then use pipeline.sh upload --dataset ACCEPTED_DIR; engineering data requires --engineering')
if __name__=='__main__':sync()
