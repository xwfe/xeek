//! K070：ManyKee 分支的读改写入口，参数和别的候选相同。走它自己的 update_entry，那才是它的应用实际用的路径。
use keepass::DatabaseKey;
use keepassxc::{fields, open_bytes, save_bytes, update_entry};
use std::{env, error::Error, fs, io};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = env::args().collect();
    let [_, input, output, entry, username] = args.as_slice() else {
        return Err("usage: input output entry-uuid username".into());
    };
    let mut password = String::new();
    io::stdin().read_line(&mut password)?;
    let key = DatabaseKey::new().with_password(password.trim_end_matches('\n'));
    let mut db = open_bytes(&fs::read(input)?, key.clone())?;
    let meta = db.meta.clone();
    update_entry(&mut db.root, entry.parse()?, &meta, |e| {
        e.set_unprotected(fields::USERNAME, username.as_str());
    })?;
    fs::write(output, save_bytes(&db, key)?)?;
    Ok(())
}
