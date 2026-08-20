#!/usr/bin/env bash

g++ -std=c++26 -Iinclude \
	main.cpp \
    -lRenderEngine-release -lavformat -lavcodec -lswscale -lavutil \
	-o main \
	-O3 -g
