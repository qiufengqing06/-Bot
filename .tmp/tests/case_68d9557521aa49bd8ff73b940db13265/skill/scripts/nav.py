import os, sys
print('args=' + '|'.join(sys.argv[1:]))
print('leak=' + os.environ.get('SHOULD_NOT_LEAK', ''))
