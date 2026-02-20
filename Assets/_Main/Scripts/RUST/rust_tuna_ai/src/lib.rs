use num_traits::Float;
use rayon::prelude::*;


#[repr(C)]
#[derive(Clone, Copy)]
pub struct Float2 {
    pub x: f32,
    pub y: f32,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct FishJobInput {
    pub index: i32,
    pub position: Float2,
    pub forward_direction: Float2,
    pub current_target_position: Float2,
    pub size: f32,
    pub current_state_int: i32,
    pub focusing_time: f32,
    pub is_player: bool,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct FishJobOutput {
    pub target_position: Float2,
    pub state_int: i32,
    pub focusing_time: f32,
}

#[inline(always)]
fn length_sq(v: Float2) -> f32 {
    v.x * v.x + v.y * v.y
}

#[inline(always)]
fn dot(a: Float2, b: Float2) -> f32 {
    a.x * b.x + a.y * b.y
}

#[inline(always)]
fn normalize(v: Float2) -> Float2 {
    let len = (v.x * v.x + v.y * v.y).sqrt();
    if len > 0.0001 {
        Float2 { x: v.x / len, y: v.y / len }
    } else {
        Float2 { x: 0.0, y: 0.0 }
    }
}

#[inline(always)]
fn distance(a: Float2, b: Float2) -> f32 {
    let dx = a.x - b.x;
    let dy = a.y - b.y;
    (dx * dx + dy * dy).sqrt()
}

#[inline(always)]
fn simple_random(seed: &mut u32) -> f32 {
    // Simple LCG
    *seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
    // Return float in [0.0, 1.0)
    (*seed as f32) / (u32::MAX as f32)
}

#[unsafe(no_mangle)]
pub extern "C" fn process_fish_ai(
    input_ptr: *const FishJobInput,
    output_ptr: *mut FishJobOutput,
    fish_count: i32,
    max_search_distance_sq: f32,
    max_vision_angle_cos: f32,
    current_time: f32,
    area_center: Float2,
    area_size: Float2,
    active_area_center: Float2,
    active_area_extents: Float2,
) {
    if input_ptr.is_null() || output_ptr.is_null() || fish_count <= 0 {
        return;
    }

    let inputs = unsafe { std::slice::from_raw_parts(input_ptr, fish_count as usize) };

    let focus_target_duration = 2.0;
    let max_search_dist_sqrt = max_search_distance_sq.sqrt();

    let mut sorted_indices: Vec<usize> = (0..(fish_count as usize)).collect();
    sorted_indices.par_sort_unstable_by(|&a, &b| {
        inputs[a].position.x.partial_cmp(&inputs[b].position.x).unwrap_or(std::cmp::Ordering::Equal)
    });

    let output_ptr_usize = output_ptr as usize;

    (0..(fish_count as usize)).into_par_iter().for_each(|k| {
        let i = sorted_indices[k];
        let own_input = &inputs[i];
        let own_size = own_input.size;
        let own_position = own_input.position;
        let mut closest_target = max_search_distance_sq;

        let mut new_target_pos = own_input.current_target_position;
        let mut new_state = own_input.current_state_int;
        let mut is_found_target = false;
        let mut focusing_time = own_input.focusing_time;

        let mut player_target_pos = Float2 { x: 0.0, y: 0.0 };
        let mut found_player = false;
        
        let mut closest_prey_pos = Float2 { x: 0.0, y: 0.0 };
        let mut closest_prey_distance = max_search_distance_sq;

        let diff_x = (own_position.x - active_area_center.x).abs();
        let diff_y = (own_position.y - active_area_center.y).abs();
        let need_to_compute = diff_x <= active_area_extents.x && diff_y <= active_area_extents.y;

        if !need_to_compute {
            unsafe {
                let out_ptr = output_ptr_usize as *mut FishJobOutput;
                *out_ptr.add(i) = FishJobOutput {
                    target_position: own_position,
                    state_int: 0, // Idle
                    focusing_time: 0.0,
                };
            }
            return;
        }

        macro_rules! check_neighbor {
            ($j:expr) => {
                if i != $j {
                    let other_fish = &inputs[$j];
                    let dist_vec = Float2 {
                        x: other_fish.position.x - own_position.x,
                        y: other_fish.position.y - own_position.y,
                    };
                    let dist_sq = length_sq(dist_vec);

                    if dist_sq <= max_search_distance_sq {
                        // check vision cone
                        let dir_to_target = normalize(dist_vec);
                        let dot_prod = dot(own_input.forward_direction, dir_to_target);
                        if dot_prod >= max_vision_angle_cos {
                            if other_fish.is_player && other_fish.size < own_size {
                                player_target_pos = other_fish.position;
                                found_player = true;
                            }

                            if !other_fish.is_player && other_fish.size < own_size {
                                if dist_sq < closest_prey_distance {
                                    closest_prey_pos = other_fish.position;
                                    closest_prey_distance = dist_sq;
                                }
                            } else if other_fish.size > own_size {
                                if dist_sq < closest_target * 1.5 || new_state != 2 { // 2 = Fleeing
                                    let flee_dir = normalize(Float2 { x: -dist_vec.x, y: -dist_vec.y }); // Fleeing away
                                    new_target_pos = Float2 {
                                        x: own_position.x + flee_dir.x * 20.0,
                                        y: own_position.y + flee_dir.y * 20.0,
                                    };
                                    new_state = 2; // Fleeing
                                    closest_target = dist_sq;
                                    is_found_target = true;
                                    focusing_time = current_time + focus_target_duration;
                                }
                            }
                        }
                    }
                }
            };
        }

        // Sweep right
        for m in (k + 1)..(fish_count as usize) {
            let j = sorted_indices[m];
            if inputs[j].position.x - own_position.x > max_search_dist_sqrt {
                break;
            }
            check_neighbor!(j);
        }

        // Sweep left
        for m in (0..k).rev() {
            let j = sorted_indices[m];
            if own_position.x - inputs[j].position.x > max_search_dist_sqrt {
                break;
            }
            check_neighbor!(j);
        }

        if found_player {
            new_target_pos = player_target_pos;
            new_state = 1; // Hunting
            is_found_target = true;
            focusing_time = current_time + focus_target_duration;
        } else if closest_prey_distance < max_search_distance_sq {
            new_target_pos = closest_prey_pos;
            new_state = 1; // Hunting
            is_found_target = true;
            focusing_time = current_time + focus_target_duration;
        }

        if new_state == 1 && is_found_target {
            let out_of_bounds =
                (new_target_pos.x - area_center.x).abs() > area_size.x / 2.0 ||
                (new_target_pos.y - area_center.y).abs() > area_size.y / 2.0;
            if out_of_bounds {
                new_target_pos = area_center;
                new_state = 0; // Idle
                focusing_time = 0.0;
            }
        }

        if !is_found_target {
            let is_out_of_bounds =
                (own_position.x - area_center.x).abs() > area_size.x / 2.0 ||
                (own_position.y - area_center.y).abs() > area_size.y / 2.0;

            if is_out_of_bounds && new_state != 1 && new_state != 2 {
                new_target_pos = area_center;
                new_state = 0;
                is_found_target = true;
                focusing_time = 0.0;
            }

            match new_state {
                2 => { // Fleeing
                    if current_time >= focusing_time {
                        new_state = 0;
                        focusing_time = 0.0;
                    } else {
                        new_target_pos = Float2 {
                            x: own_position.x + own_input.forward_direction.x * 20.0,
                            y: own_position.y + own_input.forward_direction.y * 20.0,
                        };
                    }
                },
                1 => { // Hunting
                    if current_time >= focusing_time {
                        new_state = 0;
                        focusing_time = 0.0;
                    } else {
                        new_target_pos = Float2 {
                            x: own_position.x + own_input.forward_direction.x * 20.0,
                            y: own_position.y + own_input.forward_direction.y * 20.0,
                        };
                    }
                },
                0 | _ => { // Idle
                    let target_oob =
                        (new_target_pos.x - area_center.x).abs() > area_size.x / 2.0 ||
                        (new_target_pos.y - area_center.y).abs() > area_size.y / 2.0;
                    let dist = distance(own_position, new_target_pos);
                    
                    if dist < 2.0 || target_oob {
                        // Random Wandering Position
                        let index = own_input.index;
                        let seed_base = ((index as f32 * 1000.0) + (own_position.x * 100.0) + (own_position.y * 100.0) + (current_time * 1000.0)) as u32;
                        let mut seed = seed_base.max(1);
                        
                        let rx = simple_random(&mut seed) - 0.5; // [-0.5, 0.5)
                        let ry = simple_random(&mut seed) - 0.5;
                        
                        new_target_pos = Float2 {
                            x: area_center.x + rx * area_size.x,
                            y: area_center.y + ry * area_size.y,
                        };
                    }
                    new_state = 0;
                }
            }
        }

        unsafe {
            let out_ptr = output_ptr_usize as *mut FishJobOutput;
            *out_ptr.add(i) = FishJobOutput {
                target_position: new_target_pos,
                state_int: new_state,
                focusing_time,
            };
        }
    });
}

