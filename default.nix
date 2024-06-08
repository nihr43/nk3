{ nixpkgs ? import <nixpkgs> {  } }:

let
  pkgs = with nixpkgs.python311Packages; [
    pycryptodome
    pylxd
    jinja2
    paramiko
    pyyaml
    termcolor
  ];

in
  nixpkgs.stdenv.mkDerivation {
    name = "env";
    buildInputs = pkgs;
  }
