{ nixpkgs ? import <nixpkgs> {  } }:

let
  pkgs = with nixpkgs.python311Packages; [
    pycryptodome
    pylxd
    jinja2
  ];

in
  nixpkgs.stdenv.mkDerivation {
    name = "env";
    buildInputs = pkgs;
  }
