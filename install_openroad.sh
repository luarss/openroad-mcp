#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENROAD_DIR="${OPENROAD_DIR:-${SCRIPT_DIR}/OpenROAD}"
BUILD_TYPE="${BUILD_TYPE:-RELEASE}"
ENABLE_MANPAGES="${ENABLE_MANPAGES:-false}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/usr/local}"

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Install OpenROAD from source following official build instructions.

Options:
    -h, --help              Show this help message
    -d, --dir DIR           OpenROAD source directory (default: ./OpenROAD)
    -t, --type TYPE         Build type: RELEASE or DEBUG (default: RELEASE)
    -m, --manpages          Enable building manpages
    -p, --prefix PREFIX     Installation prefix (default: /usr/local)
    --clean                 Clean existing build before building
    --deps-only             Only install dependencies, don't build
    --no-deps               Skip dependency installation

Examples:
    $0                      # Standard installation
    $0 --type DEBUG         # Debug build
    $0 --manpages           # Build with manpages
    $0 --clean              # Clean build
    $0 --deps-only          # Install dependencies only

EOF
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

check_system() {
    log "Checking system requirements..."

    if ! command -v git >/dev/null 2>&1; then
        error "Git is required but not installed"
    fi

    if ! command -v sudo >/dev/null 2>&1; then
        error "sudo is required for dependency installation"
    fi

    available_memory=$(free -m | awk 'NR==2{print $2}')
    if [ "$available_memory" -lt 4096 ]; then
        log "Warning: Less than 4GB RAM available. Build may fail or be slow."
    fi

    log "System check passed"
}

clone_repository() {
    if [ -d "$OPENROAD_DIR" ]; then
        log "OpenROAD directory already exists at $OPENROAD_DIR"
        cd "$OPENROAD_DIR"
        log "Updating repository..."
        git pull --recurse-submodules
        git submodule update --init --recursive
    else
        log "Cloning OpenROAD repository to $OPENROAD_DIR..."
        git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git "$OPENROAD_DIR"
        cd "$OPENROAD_DIR"
    fi
}

install_dependencies() {
    log "Installing base dependencies..."
    sudo ./etc/DependencyInstaller.sh -base

    log "Installing common dependencies..."
    ./etc/DependencyInstaller.sh -common -local

    log "Dependencies installed successfully"
}

build_openroad() {
    log "Building OpenROAD (Build type: $BUILD_TYPE)..."

    build_args=""

    if [ "$BUILD_TYPE" = "DEBUG" ]; then
        build_args="-cmake=-DCMAKE_BUILD_TYPE=DEBUG"
    fi

    if [ "$ENABLE_MANPAGES" = "true" ]; then
        build_args="$build_args -build-man"
    fi

    if [ -n "$INSTALL_PREFIX" ] && [ "$INSTALL_PREFIX" != "/usr/local" ]; then
        build_args="$build_args -cmake=-DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX"
    fi

    log "Build command: ./etc/Build.sh $build_args"
    ./etc/Build.sh $build_args

    log "Build completed successfully"
}

install_openroad() {
    log "Installing OpenROAD to $INSTALL_PREFIX..."

    if [ -f "build/src/openroad" ]; then
        sudo install -m 755 build/src/openroad "$INSTALL_PREFIX/bin/"
        log "OpenROAD binary installed to $INSTALL_PREFIX/bin/openroad"
    else
        error "OpenROAD binary not found at build/src/openroad"
    fi

    if [ -d "build/src/gui" ]; then
        log "GUI components found, installing..."
        sudo cp -r build/src/gui/* "$INSTALL_PREFIX/bin/" 2>/dev/null || true
    fi
}

verify_installation() {
    log "Verifying installation..."

    if command -v openroad >/dev/null 2>&1; then
        version=$(openroad -version 2>&1 | head -n1 || echo "Unknown version")
        log "OpenROAD installed successfully: $version"
    else
        if [ -f "$INSTALL_PREFIX/bin/openroad" ]; then
            version=$("$INSTALL_PREFIX/bin/openroad" -version 2>&1 | head -n1 || echo "Unknown version")
            log "OpenROAD installed at $INSTALL_PREFIX/bin/openroad: $version"
            log "Add $INSTALL_PREFIX/bin to your PATH to use 'openroad' command"
        else
            error "OpenROAD installation verification failed"
        fi
    fi
}

clean_build() {
    if [ -d "$OPENROAD_DIR/build" ]; then
        log "Cleaning existing build directory..."
        rm -rf "$OPENROAD_DIR/build"
    fi
}

main() {
    local clean=false
    local deps_only=false
    local no_deps=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -d|--dir)
                OPENROAD_DIR="$2"
                shift 2
                ;;
            -t|--type)
                BUILD_TYPE="$2"
                if [[ "$BUILD_TYPE" != "RELEASE" && "$BUILD_TYPE" != "DEBUG" ]]; then
                    error "Build type must be RELEASE or DEBUG"
                fi
                shift 2
                ;;
            -m|--manpages)
                ENABLE_MANPAGES=true
                shift
                ;;
            -p|--prefix)
                INSTALL_PREFIX="$2"
                shift 2
                ;;
            --clean)
                clean=true
                shift
                ;;
            --deps-only)
                deps_only=true
                shift
                ;;
            --no-deps)
                no_deps=true
                shift
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done

    log "Starting OpenROAD installation..."
    log "Source directory: $OPENROAD_DIR"
    log "Build type: $BUILD_TYPE"
    log "Install prefix: $INSTALL_PREFIX"

    check_system
    clone_repository

    if [ "$clean" = true ]; then
        clean_build
    fi

    if [ "$no_deps" != true ]; then
        install_dependencies
    fi

    if [ "$deps_only" = true ]; then
        log "Dependencies installation completed. Skipping build as requested."
        exit 0
    fi

    build_openroad
    install_openroad
    verify_installation

    log "OpenROAD installation completed successfully!"
    log "Binary location: $INSTALL_PREFIX/bin/openroad"

    if [[ ":$PATH:" != *":$INSTALL_PREFIX/bin:"* ]]; then
        log ""
        log "To use OpenROAD, add the following to your shell profile:"
        echo "export PATH=\"$INSTALL_PREFIX/bin:\$PATH\""
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
