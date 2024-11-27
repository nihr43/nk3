{ nixpkgs ? import <nixpkgs> {  } }:

let
  pkgs = with nixpkgs.python312Packages; [
    pycryptodome
    pylxd
    jinja2
    fabric
    paramiko
    pyyaml
    termcolor
  ];

in
  nixpkgs.stdenv.mkDerivation {
    name = "env";
    buildInputs = pkgs;
  }
