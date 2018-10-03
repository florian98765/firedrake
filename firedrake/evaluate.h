#ifndef _EVALUATE_H
#define _EVALUATE_H

#include <petsc.h>

#ifdef __cplusplus
extern "C" {
#endif

struct Function {
	/* Number of cells in the base mesh */
	int n_cols;

	/* Number of layers for extruded, otherwise 1 */
	int n_layers;

	/* Coordinate values and node mapping */
	PetscScalar *coords;
	PetscInt *coords_map;

	/* Field values and node mapping */
	PetscScalar *f;
	PetscInt *f_map;

	/* Spatial index */
	void *sidx;

	/*
	 * TODO:
	 * - cell orientation
	 */
};

typedef int (*inside_predicate)(void *data_,
				struct Function *f,
				int cell,
				PetscScalar *x);


extern int locate_cell(struct Function *f,
		       PetscScalar *x,
		       int dim,
		       inside_predicate try_candidate,
		       void *data_);

extern int evaluate(struct Function *f,
		    PetscScalar *x,
		    PetscScalar *result);

#ifdef __cplusplus
}
#endif

#endif /* _EVALUATE_H */
