# ==============================================================================
# Example ESP-IDF Component CMakeLists.txt for epd-font (v1.0.23)
# A 1-bit EPD font generator and asset pipeline for embedded displays
# Repository : https://github.com/Humidyne-Labs/epd-font
# Target SoC : ESP32-S3-N8R8 (H1OS / LVGL >= 9.6.0)
# ==============================================================================

cmake_minimum_required(VERSION 3.16)

set(EPD_FONT_SCHEME "${CMAKE_CURRENT_LIST_DIR}/schemes/h1os_full.scheme.json" CACHE FILEPATH "Declarative epd-font scheme JSON")
set(EPD_FONT_VAULT  "${CMAKE_CURRENT_LIST_DIR}/humid1_epd_vault.json.gz" CACHE FILEPATH "Pre-rasterized epd-font Strike Vault")
option(EPD_FONT_USE_PREGENERATED "Compile pre-generated fonts/*.c without invoking Python vault emitter" OFF)

if(ESP_PLATFORM OR DEFINED IDF_TARGET OR COMMAND idf_component_register)
    if(CMAKE_BUILD_EARLY_EXPANSION)
        idf_component_register(
            REQUIRES lvgl
        )
        return()
    endif()

    if(EPD_FONT_USE_PREGENERATED OR NOT EXISTS "${EPD_FONT_VAULT}")
        file(GLOB EPD_FONT_C_FILES CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/fonts/*.c")
        idf_component_register(
            SRCS ${EPD_FONT_C_FILES}
            INCLUDE_DIRS "fonts"
            REQUIRES lvgl
        )
    else()
        find_package(Python3 COMPONENTS Interpreter REQUIRED)
        set(EPD_FONT_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated_fonts")
        file(MAKE_DIRECTORY "${EPD_FONT_OUT_DIR}")

        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
            "${EPD_FONT_VAULT}"
            "${EPD_FONT_SCHEME}"
        )

        execute_process(
            COMMAND "${Python3_EXECUTABLE}"
                "${CMAKE_CURRENT_LIST_DIR}/tools/humid1_cmake_font_builder.py"
                "--scheme"  "${EPD_FONT_SCHEME}"
                "--vault"   "${EPD_FONT_VAULT}"
                "--out-dir" "${EPD_FONT_OUT_DIR}"
            RESULT_VARIABLE EPD_FONT_RESULT
        )
        if(NOT EPD_FONT_RESULT EQUAL 0)
            message(FATAL_ERROR "[epd-font] Font generation from Strike Vault failed with exit code ${EPD_FONT_RESULT}")
        endif()

        include("${EPD_FONT_OUT_DIR}/epd_fonts_manifest.cmake")
        idf_component_register(
            SRCS ${EPD_FONT_C_FILES}
            REQUIRES lvgl
        )
        target_include_directories(${COMPONENT_LIB} PUBLIC "${EPD_FONT_OUT_DIR}")
    endif()
else()
    include("${CMAKE_CURRENT_LIST_DIR}/cmake/epd_font_esp_idf.cmake")

    epd_font_add_library(
        TARGET  humid1_epd_fonts
        SCHEME  "${EPD_FONT_SCHEME}"
        VAULT   "${EPD_FONT_VAULT}"
        OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated_fonts"
    )
endif()
