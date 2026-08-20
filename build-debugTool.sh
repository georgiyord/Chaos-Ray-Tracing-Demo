#!/usr/bin/env bash
IMGUI_DIR=./imgui

g++ -std=c++26 -Iimgui -Iimgui/backends -g \
	debugTool.cpp \
    $IMGUI_DIR/imgui.cpp \
    $IMGUI_DIR/imgui_demo.cpp \
    $IMGUI_DIR/imgui_draw.cpp \
    $IMGUI_DIR/imgui_tables.cpp \
    $IMGUI_DIR/imgui_widgets.cpp \
    $IMGUI_DIR/backends/imgui_impl_glfw.cpp \
    $IMGUI_DIR/backends/imgui_impl_opengl3.cpp \
    -lGL -lglfw -lrt -lm -ldl -lRenderEngine-releaseWithSymbols \
	-O0 \
	-o debugTool
