"""PDBBind dataset processed by MoleculeNet."""
import os

from ..utils import multiprocess_load_molecules
from ...utils import get_download_dir, download, _get_dgl_url, extract_archive
from .... import backend as F

class PDBBind(object):
    """PDBbind dataset processed by MoleculeNet.

    The description below is mainly based on
    `[1] <https://pubs.rsc.org/en/content/articlelanding/2018/sc/c7sc02664a#cit50>`__.
    The PDBbind database consists of experimentally measured binding affinities for
    bio-molecular complexes `[2] <https://www.ncbi.nlm.nih.gov/pubmed/?term=15163179%5Buid%5D>`__,
    `[3] <https://www.ncbi.nlm.nih.gov/pubmed/?term=15943484%5Buid%5D>`__. It provides detailed
    3D Cartesian coordinates of both ligands and their target proteins derived from experimental
    (e.g., X-ray crystallography) measurements. The availability of coordinates of the
    protein-ligand complexes permits structure-based featurization that is aware of the
    protein-ligand binding geometry. The authors of
    `[1] <https://pubs.rsc.org/en/content/articlelanding/2018/sc/c7sc02664a#cit50>`__ use the
    "refined" and "core" subsets of the database
    `[4] <https://www.ncbi.nlm.nih.gov/pubmed/?term=25301850%5Buid%5D>`__, more carefully
    processed for data artifacts, as additional benchmarking targets.

    References:

        * [1] MoleculeNet: a benchmark for molecular machine learning
        * [2] The PDBbind database: collection of binding affinities for protein-ligand complexes
        with known three-dimensional structures
        * [3] The PDBbind database: methodologies and updates
        * [4] PDB-wide collection of binding data: current status of the PDBbind database

    Parameters
    ----------
    subset_choice : str
        In MoleculeNet, we can use either the "refined" subset or the "core" subset. We can
        retrieve them by setting ``subset_choice`` to be ``'refined'`` or ``'core'``. The size
        of the ``'core'`` set is 195 and the size of the ``'refined'`` set is 3706.
    load_binding_pocket : bool
        Whether to load binding pockets or full proteins. Default to False.
    add_hydrogens : bool
        Whether to add hydrogens via pdbfixer. Default to True.
    sanitize : bool
        Whether sanitization is performed in initializing RDKit molecule instances. See
        https://www.rdkit.org/docs/RDKit_Book.html for details of the sanitization.
        Default to False.
    calc_charges : bool
        Whether to add Gasteiger charges via RDKit. Setting this to be True will enforce
        ``add_hydrogens`` and ``sanitize`` to be True. Default to True.
    remove_hs : bool
        Whether to remove hydrogens via RDKit. Note that removing hydrogens can be quite
        slow for large molecules. Default to False.
    use_conformation : bool
        Whether we need to extract molecular conformation from proteins and ligands.
        Default to True.
    num_processes : int or None
        Number of worker processes to use. If None,
        then we will use the number of CPUs in the systetm. Default to None.
    """
    def __init__(self, subset_choice, load_binding_pocket=False, add_hydrogens=False,
                 sanitize=True, calc_charges=False, remove_hs=False, use_conformation=True,
                 num_processes=None):
        self.task_names = ['-logKd/Ki']
        self.n_tasks = len(self.task_names)

        self._url = 'dataset/pdbbind_v2015.tar.gz'
        root_dir_path = get_download_dir()
        data_path = root_dir_path + '/pdbbind_v2015.tar.gz'
        extracted_data_path = root_dir_path + '/pdbbind_v2015'
        download(_get_dgl_url(self._url), path=data_path)
        extract_archive(data_path, extracted_data_path)

        if subset_choice == 'core':
            index_label_file = extracted_data_path + '/v2015/INDEX_core_data.2013'
        elif subset_choice == 'refined':
            index_label_file = extracted_data_path + '/v2015/INDEX_refined_data.2015'
        else:
            raise ValueError(
                'Expect the subset_choice to be either '
                'core or refined, got {}'.format(subset_choice))

        self._preprocess(extracted_data_path, index_label_file, load_binding_pocket,
                         add_hydrogens, sanitize, calc_charges, remove_hs, use_conformation,
                         num_processes)

    def _filter_out_invalid(self, proteins_loaded, ligands_loaded, use_conformation):
        """Filter out invalid ligand-protein pairs.

        Parameters
        ----------
        """
        num_pairs = len(proteins_loaded)
        self.protein_mols = []
        self.ligand_mols = []
        if use_conformation:
            self.ligand_coordinates = []
            self.protein_coordinates = []

        for i in range(num_pairs):
            protein_mol, protein_coordinates = proteins_loaded[i]
            ligand_mol, ligand_coordinates = ligands_loaded[i]
            if (not use_conformation) and all(v is not None for v in [protein_mol, ligand_mol]):
                self.protein_mols.append(protein_mol)
                self.ligand_mols.append(ligand_mol)
            elif all(v is not None for v in [
                protein_mol, protein_coordinates, ligand_mol, ligand_coordinates]):
                self.protein_mols.append(protein_mol)
                self.protein_coordinates.append(protein_coordinates)
                self.ligand_mols.append(ligand_mol)
                self.ligand_coordinates.append(ligand_coordinates)

    def _preprocess(self, root_path, index_label_file, load_binding_pocket,
                    add_hydrogens, sanitize, calc_charges, remove_hs, use_conformation,
                    num_processes):
        """Preprocess the dataset.

        The pre-processing proceeds as follows:

        1. Load the dataset
        2. Clean the dataset and filter out invalid pairs
        3. Construct graphs
        4. Prepare node and edge features

        Parameters
        ----------
        """
        pdbs = []
        labels = []
        with open(index_label_file, 'r') as f:
            for line in f.readlines():
                if line[0] != "#":
                    # Get the location of all ligand-protein pairs
                    pdbs.append(line[:4])
                    labels.append(float(line.split()[3]))
        self.labels = F.reshape(F.tensor(labels), (-1, 1))

        if load_binding_pocket:
            self.protein_files = [os.path.join(
                root_path, 'v2015', pdb, '{}_pocket.pdb'.format(pdb)) for pdb in pdbs]
        else:
            self.protein_files = [os.path.join(
                root_path, 'v2015', pdb, '{}_protein.pdb'.format(pdb)) for pdb in pdbs]
        self.ligand_files = [os.path.join(
            root_path, 'v2015', pdb, '{}_ligand.sdf'.format(pdb)) for pdb in pdbs]

        print('Loading proteins...')
        proteins_loaded = multiprocess_load_molecules(self.protein_files,
                                                      add_hydrogens=add_hydrogens,
                                                      sanitize=sanitize,
                                                      calc_charges=calc_charges,
                                                      remove_hs=remove_hs,
                                                      use_conformation=use_conformation,
                                                      num_processes=num_processes)

        print('Loading ligands...')
        ligands_loaded = multiprocess_load_molecules(self.ligand_files,
                                                     add_hydrogens=add_hydrogens,
                                                     sanitize=sanitize,
                                                     calc_charges=calc_charges,
                                                     remove_hs=remove_hs,
                                                     use_conformation=use_conformation,
                                                     num_processes=num_processes)
        self._filter_out_invalid(proteins_loaded, ligands_loaded, use_conformation)

    def __len__(self):
        return len(self.ligand_mols)