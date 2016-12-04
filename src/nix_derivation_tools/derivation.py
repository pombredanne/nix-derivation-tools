import ast
import os
import json

import datadiff
import yaml
import rtyaml


class Derivation(object):
    """A Python representation of a derivation."""
    def __init__(self, path, outputs, input_derivations, input_files, system,
                 builder, builder_args, environment):
        """Initializer.

        :param path: The path to this derivation file.
        :type path: ``str``
        :param outputs: The outputs this derivation will produce. Keys are
            output names, and values are EITHER nix store paths, OR
            nix store paths plus some output hash information.
        :type outputs: ``dict`` of ``str`` -> ``str``
        :param input_derivations: Derivations required to build the
            expression. Keys are derivation paths, and values are lists of
            output names that this derivation will use.
        :type input_derivations: ``dict`` of ``str`` -> ``list`` of ``str``
        :param input_files: Store paths that aren't derivations, which
            are needed to build the expression.
        :type input_files: ``set`` of ``str``
        :param system: Architecture and OS the derivation is built on.
        :type system: ``str``
        :param builder: Store path of the derivation's builder executable.
        :type builder: ``str``
        :param builder_args: Command-line arguments for the builder.
        :type builder_args: ``list`` of ``str``
        :param environment: Environment variables to set for the builder.
        :type environment: ``dict`` of ``str`` to ``str``
        """
        self.outputs = outputs
        self.input_derivations = input_derivations
        self.input_files = input_files
        self.system = system
        self.builder = builder
        self.builder_args = builder_args
        self.environment = environment

    @property
    def name(self):
        """Get the name of the derivation by reading its environment.

        `name` is required so this should be safe.
        """
        return self.environment["name"]

    @property
    def input_paths(self):
        """Set of all store paths needed to build the derivation.

        :return: A set of paths.
        :rtype: ``set`` of ``str``
        """
        paths = set(self.input_files)
        for deriv_path, outputs in self.input_derivations.items():
            input_deriv = Derivation.parse_derivation_file(deriv_path)
            for output in outputs:
                paths.add(input_deriv.outputs[output])
        return paths

    @property
    def output_names(self):
        """Return the names of outputs that this derivation produces.

        :return: A set of output names.
        :rtype: ``set`` of ``str``
        """
        return set(self.outputs.keys())

    def __eq__(self, other):
        """Test if one derivation is equal to another."""
        return vars(self) == vars(other)

    def to_dict(self):
        """Convert to a JSON-compatible dictionary."""
        res = vars(self)
        for key, val in res.items():
            if isinstance(val, (set, tuple)):
                res[key] = list(val)
        return res

    def diff(self, other):
        """Get a naive diff between two derivations, just comparing
        their dictionary representation."""
        selfdict, otherdict = vars(self), vars(other)
        # Convert outputs to a format that doesn't include the output
        # file path, since we know this will be different if the two
        # derivations are different.
        selfdict["outputs"] = list(sorted(selfdict["outputs"].keys()))
        otherdict["outputs"] = list(sorted(otherdict["outputs"].keys()))
        return datadiff.diff(selfdict, otherdict)

    def display(self, attribute=None, env_var=None,
                format="json", pretty=False):
        """Return a string representation in the given format.

        :param attribute: If given, only show that attribute.
        :type attribute: ``str`` or ``NoneType``
        :param env_var: If given, only show that environment variable.
        :type env_var: ``str`` or ``NoneType``
        :param format: The output format. Valid options are 'json' and 'yaml'.
        :type format: ``str``
        :param pretty: Pretty-print.
        :type pretty: ``bool``

        :rtype: ``str``
        """
        selfdict = self.to_dict()
        if attribute is None and env_var is None:
            to_print = selfdict
        elif attribute is not None:
            to_print = selfdict[attribute]
        else:
            to_print = self.environment[env_var]
        if isinstance(to_print, str) and pretty is True:
            return to_print
        if format == "json":
            if pretty is True:
                return json.dumps(to_print, indent=2)
            else:
                return json.dumps(to_print)
        elif format == "yaml":
            if pretty is True:
                return rtyaml.dump(to_print)
            else:
                return yaml.dump(to_print)
        else:
            raise ValueError("Invalid format: {}".format(format))

    @staticmethod
    def parse_derivation(derivation_string, derivation_path):
        """Parse a derivation string into a Derivation.

        :param derivation_string: A string representation of a
            derivation, as returned by a call to `nix-instantiate`.
        :type derivation_string: ``str``
        :param derivation_path: Path to the derivation file.
        :type derivation_path: ``str``

        :return: The parsed Derivation object.
        :rtype: :py:class:`Derivation`
        """
        if derivation_string.startswith("Derive(["):
            # Then trim off the initial 'Derive(' and final ')'
            derivation_string = derivation_string[7:-1]
        # Parse the string as a python literal; this is a safe
        # operation because the derivation will not contain any
        # function calls, or anything which isn't a valid python literal.
        derivation_list =  ast.literal_eval(derivation_string)
        outputs = {name: path if hashtype == "" else (path, hashtype, hash_)
                   for name, path, hashtype, hash_ in derivation_list[0]}
        input_derivations = dict(derivation_list[1])
        input_files = set(derivation_list[2])
        system = derivation_list[3]
        builder = derivation_list[4]
        builder_args = derivation_list[5]
        environment = dict(derivation_list[6])
        return Derivation(path=derivation_path,
            outputs=outputs, input_derivations=input_derivations,
            input_files=input_files, system=system, builder=builder,
            builder_args=builder_args, environment=environment)

    @staticmethod
    def parse_derivation_file(derivation_path):
        """Parse a derivation from a file path.

        :param derivation_path: Path to a file containing a string
            representation of a derivation.
        :type derivation_path: ``str``

        :return: The parsed Derivation object.
        :rtype: :py:class:`Derivation`
        """
        if not os.path.isabs(derivation_path) and "NIX_STORE" in os.environ:
            derivation_path = os.path.join(os.environ["NIX_STORE"],
                                           derivation_path)
        with open(derivation_path, "rb") as f:
            source = f.read().decode("utf-8")
            try:
                return Derivation.parse_derivation(source, derivation_path)
            except Exception as e:
                raise ValueError("Couldn't parse derivation at path {}: {}"
                                 .format(derivation_path, repr(e)))
