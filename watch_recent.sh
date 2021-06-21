#!/bin/bash
latest_dir=$(ls -t nle_data/ | head -n1)
nth_file=$(ls -t nle_data/${latest_dir} | tail -n$1 | head -n1)
echo $nth_file
speed=0.01
if [ $# -eq 2 ];
then
	speed=$2
fi
poetry run nle-ttyplay -s $speed nle_data/${latest_dir}/$nth_file
